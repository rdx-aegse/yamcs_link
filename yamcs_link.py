# -*- coding: utf-8 -*-

"""
Module: yamcs_link.py

Main module, see README.md for more information

Author: gmarchetx

Created on: Thu Feb 13 16:46:35 2025

"""

### Import and config #############################################################################################################

import socket
import select
import time
import signal
import sys
import logging
from typing import override

from yamcs_userlib import YAMCSContainer, EventSeverity
from yamcs_mdb_generator.yamcs_mdb_gen import YAMCSMDBGen
from utils import SerDer

# Configure logging - TODO: feels odd having this here, to be checked
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

### Public classes #############################################################################################################

class YAMCS_link(YAMCSContainer):
    """
    A class to manage the link between a YAMCSContainer and YAMCS, handling
    telemetry sending and telecommand receiving in a single-threaded manner.
    """

    #Describes the format of the command header (to be deserialised, uses the dict structure of SerDer)
    COMMAND_HEADER_FORMAT = [
        {'name': 'start_word', 'type': 'U32'},
        {'name': 'opcode', 'type': YAMCSMDBGen.OPCODE_TYPE} #Opcodes are present in mdbs
    ]
    #Start word of commands received
    START_WORD = 0xFEEDCAFE
    #Describes the format of the telemetry header (to be serialised, uses the dict structure of SerDer)
    TM_HEADER_FORMAT = [
        {'name': 'PacketType', 'type': YAMCSMDBGen.PACKETTYPE_TYPE}, #PacketType, to support events in the future. Present in mdbs
        {'name': 'PacketID', 'type': YAMCSMDBGen.PACKETID_TYPE} #PacketID to determine the format (id = index of TM refresh interval). Present in mdbs.
    ]
    #VAlue of the packet type field in an outgoing packet header, when the packet is TM (not events)
    TM_PACKETTYPE_VAL = YAMCSMDBGen.PACKETTYPE_TLM
    
    #Value of the packet type field in an outgoing packet header, when the packet is an event
    EVENTS_PACKETTYPE_VAL = YAMCSMDBGen.PACKETTYPE_EVENT
    #Size of the buffer for the source of any event = max length of the full source name (YAMCSObject.yamcs_name) including the terminating char
    EVENT_SOURCESTR_SIZE = 80
    #Size of the buffer for the message of any event = max length of the message of any event including the terminating char
    EVENT_MSG_SIZE = 256
    #Corresponding YAMCS data types for event strings
    EVENT_MSG_TYPE = f"string{EVENT_MSG_SIZE}"
    EVENT_SOURCESTR_TYPE = f"string{EVENT_SOURCESTR_SIZE}"
    #Describes the format of the full event message (to be serialised, uses the dict structure of SerDer)
    EVENT_PACKET_FORMAT = [
        {'name': 'PacketType', 'type': YAMCSMDBGen.PACKETTYPE_TYPE}, #PacketType, to allow multiplexing events and TM
        {'name': 'PacketID', 'type': YAMCSMDBGen.PACKETID_TYPE}, #PacketID, to comply with the same abstract packet format of TM when they go through the same preprocessor
        {'name': 'severity', 'type': 'U8'}, #Severity among yamcs_userlib.EventSeverity enum
        {'name': 'source', 'type': EVENT_SOURCESTR_TYPE}, #Name of the source of the event
        {'name': 'message', 'type': EVENT_MSG_TYPE}, #Formatted message for the event
    ]
    
    #Maximum size in bytes of a packet, buffer size for recv()
    MAX_PACKET_SIZE = 1024

    def __init__(self, name : str, tcp_port: int, udp_port: int):
        """
        Initializes the YAMCS_link with a YAMCSContainer and TCP/UDP ports.

        Args:
            name: the name of the yamcs_link, will become the root of the full name of tm and tc
            tcp_port: The TCP port to listen for commands from YAMCS.
            udp_port: The UDP port to send telemetry to YAMCS.
        """
        super().__init__(name)
        
        #Serialisers/deserialisers are used to simplify sending/receiving in fixed formats
        #Set them up for tm, tc and events to speed up execution 
        self.command_header_serder = SerDer(self.COMMAND_HEADER_FORMAT) 
        self.tm_header_serder = SerDer(self.TM_HEADER_FORMAT)
        self.event_serder = SerDer(self.EVENT_PACKET_FORMAT)
        # Tracks last telemetry send time for each period, will be filled in in update_index()
        self.last_tm_send_time = {}  

        #Sockets initialisation
        self.tcp_port = tcp_port
        self.udp_port = udp_port
        self.tcp_server_socket = None
        self.tcp_client_socket = None  # Socket connected to YAMCS
        self.udp_socket = None
        self.udp_target = ('localhost', self.udp_port)  # TM
        self.monitored_sock = []  # List of sockets to monitor with select()
        #Opening sockets
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._start_tcp_server()
        
        # Set up signal handling for  graceful _shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, sig, frame):
        """Handles signals for graceful _shutdown."""
        logging.info(f"Received signal {sig}. Shutting down...")
        self._shutdown()
        sys.exit(0)
        
    def _start_tcp_server(self):
        """Starts the TCP server to listen for connection requests from YAMCS"""
        try:
            logging.info(f"Starting TCP server on port {self.tcp_port}... ")
            
            self.tcp_server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_server_socket.setblocking(False) #No blocking because single-threaded app
            self.tcp_server_socket.bind(('localhost', self.tcp_port))
            self.tcp_server_socket.listen(1)
            self.monitored_sock = [self.tcp_server_socket]  # Start monitoring the server socket
            
            logging.info(f"Started. Listening for client connections")

        except Exception as e:
            logging.error(f"Error starting TCP server: {e}")
            self._shutdown()
            sys.exit(1)

    def generate_mdb(self, output_dir: str, name_mdb: str, version: str):
        """
        Generates the YAMCS mission database CSV files.

        Args:
            output_dir: The directory to save the generated CSV files.
            name_mdb: The name of the mission database.
            version: The version of the mission database.
        """
        #Build the tm and tc data from all the YAMCSObject objects that have been registered to this link before generation
        #this is the only time this is done in the library, because generating the mdb is assumed to be done at every execution prior to opening the sockets
        self.update_index()

        try:
            mdb_generator = YAMCSMDBGen(name_mdb, version, output_dir)

            # Add enums, aggregates, and arrays types
            for enum_name, values in self.get_enums().items():
                mdb_generator.addEnumType(enum_name, self.ENUM_REPR_TYPE, values)

            # Add TM packets
            tm_def = self.get_tm_def()
            for i, (period, tm_list) in enumerate(tm_def.items()):
                packet = mdb_generator.TMPacket(name=f'tm-{self.yamcs_name}-{period}ms', id=i, frequency=period)  #TODO: fix YAMCSMDBGen, it's not a frequency
                for tm in tm_list:
                    packet.addParam(tm['name'], tm['type'])
                mdb_generator.addTMTC(packet)

            # Add telecommands
            tc_def = self.get_tc_def()
            for opcode, tc in tc_def.items():
                command = mdb_generator.Command(name=tc['name'], opcode=opcode)
                for arg_name, arg_info in tc['args'].items():
                    command.addParam(arg_name, arg_info['type'], min=arg_info['min'], max=arg_info['max'])
                mdb_generator.addTMTC(command)

            mdb_generator.generateCSVs()

            logging.info(f"Mission database {name_mdb} generated successfully in {output_dir}")

        except Exception as e:
            logging.error(f"Error generating mission database: {e}")
            self._shutdown()
            sys.exit(1)

    def service(self):
        """
        Handles telemetry sending and command receiving in a non-blocking manner.
        This method should be called repeatedly in a main loop.
        """
        try:
            # Select takes care of monitoring for incoming data in the monitored sockets
            # i.e. either the server socket (listening for connection requests) or the client socket
            # created after the connection's been accepted (listening for commands)
            readable, _, _ = select.select(self.monitored_sock, [], [], 0)  # 0s timeout = do not block

            for sock in readable:
                if sock is self.tcp_server_socket:
                    # Accept new connection
                    conn, addr = self.tcp_server_socket.accept()
                    self.tcp_client_socket = conn
                    self.tcp_client_socket.setblocking(False) #non blocking because single threaded app
                    self.monitored_sock.append(self.tcp_client_socket)  # Monitor the new client socket
                    logging.info(f"Accepted connection from {addr}")
                elif sock is self.tcp_client_socket:
                    # Handle data from the client
                    data = self.tcp_client_socket.recv(self.MAX_PACKET_SIZE)
                    if data:
                        self.handle_command(data)
                    else:
                        # Connection closed
                        logging.info("Client disconnected.")
                        self._close_tcp_connection()

            # Service telemetry whenever the TCP link is active (i.e. YAMCS is connected)
            if self.tcp_client_socket:
                self.send_telemetry()

        except Exception as e:
            logging.error(f"Error in service loop: {e}")
            self._close_tcp_connection()  

    def send_telemetry(self):
        """
        Telemetry are grouped in fixed sequences by refresh period. 
        Check if any group is due for sending, and if it is serialise the telemetry sequence, packetize it and send it
        """
        try:
            current_time = time.time()
            for i_period, period in enumerate(self.get_tm_periods()):
                #If last_tm_send_time does not exist for that period, initialise it
                if period not in self.last_tm_send_time:
                    self.last_tm_send_time[period] = 0

                #if this tm group is due for sending
                if current_time - self.last_tm_send_time[period] >= period/1000: #time.time() yields seconds, not ms
                    #Update and retrieve the serialised tm data (TODO: rename method) for that group
                    tm_data = self.get_tm_values(period)
                    if tm_data:
                        #Serialise the header i.e. the packet type (TM) and the packet id (index of the group)
                        header_bytes = self.tm_header_serder.serialise([self.TM_PACKETTYPE_VAL, i_period])
                        #Append the tm data and send it
                        self.udp_socket.sendto(header_bytes+bytes(tm_data), self.udp_target)
                    #If the tm data is empty, this still counts as sending
                    self.last_tm_send_time[period] = current_time
        except Exception as e:
            logging.error(f"Telemetry sending error: {e}")

    def handle_command(self, data: bytes):
        """
        Handles incoming command data from the TCP connection.
        
        Args:
            data: byte stream coming directly from YAMCS
        """
        
        #TODO: TCP is a streaming protocol, support segmentation at any point in a command
        #Should be fine in the meantime if commands are not sent as bursts

        #Check there is enough data to check the header at least
        header_size = self.command_header_serder.minsize
        if len(data) < header_size:
            logging.warning("Incomplete command received (too short). Dropping.")
            return

        try:
            logging.info(f"Received command: {data.hex()}")
            
            #Deserialise the header and check the start word
            
            header = self.command_header_serder.deserialise(data)
            
            start_word = int(header['start_word'])
            if start_word != self.START_WORD:
                logging.warning(f"Invalid start word: 0x{start_word:X}. Dropping command.")
                return

            #Check the opcode is allowed
            opcode = header['opcode']
            if(opcode >= len(self.commands)):
                logging.warning("Command opcode is out of bounds, ignoring command.")
                return

            #Based on the opcode, check the size of the command is expected (driven by arguments data)
            if len(data) < header_size+self.commands[opcode]['serder'].minsize:
                logging.warning(f"Incomplete command received (expected length: {self.commands[opcode]['serder'].minsize}, received: {len(data)}). Dropping.")
                return

            #If all's well execute the command (will call the appropriate bound method tagged by @telecommand)
            result = self.call_tc(opcode, data[header_size:])
            
            logging.info(f"Command {opcode} (0x{opcode:X}) {self.commands[opcode]['fullname']} executed. Result: {result}")

        except Exception as e:
            logging.error(f"Command handling error: {e}")
       
    @override    
    def send_event(self, severity: EventSeverity, source: str, message: str):
        '''
        When a method tagged by the @event decorator gets called, send_event() in the base class YAMCSCOntainer just passes the event up the chain. 
        This override is meant to actually send the event to YAMCS when it the event has reached this point in the chain.
        
        Args:
            severity: severity specified in the argument of the @event decorator
            source: yamcs_name of the source instance
            message: pre-formatted event message 
        '''
        #Let's use the TM packet serder to make the preprocessor checks easier, the packet ID will just be 0 for events. 
        #The packet type is different from the TM packet types, this is what will separate packets on the other end.
        #Currently, the time stamp is given by YAMCS when receiving the event packet
        self.udp_socket.sendto(self.event_serder.serialise([
                self.EVENTS_PACKETTYPE_VAL, 
                0, #Packet ID is unused
                severity.value,
                source,
                message
            ]), self.udp_target)
            
    def _recursively_call_on_disconnect(self, obj):
        """
        Like the name suggests, call on_disconnect on all yamcs children
        """
        #Recursively call on_disconnect() on all children
        for yamcs_child in obj.children:
            if isinstance(yamcs_child, YAMCSContainer):
                self._recursively_call_on_disconnect(yamcs_child)
            
            yamcs_child.on_disconnect()

    def _close_tcp_connection(self):
        """Closes the TCP connection and cleans up."""
        if self.tcp_client_socket:
            self.monitored_sock.remove(self.tcp_client_socket)
            self.tcp_client_socket.close()
            self.tcp_client_socket = None
            logging.info("TCP connection closed.")
            
            self._recursively_call_on_disconnect(self)

    def _shutdown(self):
        """Shuts down the TCP server and UDP socket."""
        self._close_tcp_connection()

        if self.tcp_server_socket:
            self.tcp_server_socket.close()
            logging.info("TCP server socket closed.")

        if self.udp_socket:
            self.udp_socket.close()
            logging.info("UDP socket closed.")

        logging.info("YAMCS_link _shutdown complete.")


### Unit testing and usage #################################################################################

if __name__ == '__main__':
    from yamcs_userlib import YAMCSObject, telemetry, telecommand, event, U8, U16, F32, I16
    from enum import Enum
    from typing import override

    #Constants
    YAMCS_TC_PORT = 10000
    YAMCS_TM_PORT = 10001
    DIR_MDB_OUT = "/mdb_shared"
    MDB_NAME = "test"
    VERSION = "1.0"

    #Dummy example app definition
    
    class MyEnum(Enum):
        VALUE1=1
        VALUE2=2

    class MyComponent(YAMCSObject):
        def __init__(self, name):
            YAMCSObject.__init__(self, name)
        
        #Optional but highly recommended on_disconnect
        @override
        def on_disconnect(self):
            logging.info(f'{self.yamcs_name} would now go back to safe state after YAMCS disconnected')

        @telemetry(1000) #milliseconds period
        def my_telemetry1(self) -> MyEnum:
            return MyEnum.VALUE1.value

        @telemetry(2000) #milliseconds period
        def my_telemetry2(self) -> U8:
            return 42

        @telecommand(arg1=[5,10], arg3=[None, 1000])
        def my_command(self, arg1: U16, arg2: I16, arg3: F32) -> U8:
            logging.info(f'MyComponent.my_command was invoked on {self.yamcs_name} with args {arg1}, {arg2}, {arg3}')
            logging.info(f'Triggering event my_event')
            self.my_event(arg1, arg2)
            return 0
        
        @event(EventSeverity.INFO)
        def my_event(self, arg1 : U16, arg2 : F32) -> str:
            return f'Dummy event triggered with arguments arg1={arg1} and arg2={arg2}'
        
    #initialisation
    yamcs_link = YAMCS_link("my_link", tcp_port=YAMCS_TC_PORT, udp_port=YAMCS_TM_PORT) 
    my_component = MyComponent("component1")
    yamcs_link.register_yamcs_child(my_component)

    #Generate mdb is necessary for YAMCS to know how to interact with the app. 
    # Make sure there is an automated process for yamcs to start up from those updated mdb
    yamcs_link.generate_mdb(DIR_MDB_OUT, MDB_NAME, VERSION) 
    #If the mdb is generated through some other scheme, manually do call update_index() between register_yamcs_child() and service()

    # Main loop
    try:
        while True:
            #Possible to do things here e.g. if your app doesn't inherit from YAMCS_link
            yamcs_link.service() #Send due TM and process pending command then return
            time.sleep(0.1) #Small delay to prevent busy-waiting
    except KeyboardInterrupt:
        logging.info("Exiting main loop.")
    finally:
        yamcs_link._shutdown() 
