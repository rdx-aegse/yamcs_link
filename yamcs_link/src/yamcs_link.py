# yamcs_link.py
import socket
import select
import time
import signal
import sys
import logging

from yamcs_userlib import YAMCSContainer  
from yamcs_mdb_gen import YAMCSMDBGen
from utils import SerDer

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class YAMCS_link(YAMCSContainer):
    """
    A class to manage the link between a YAMCSContainer and YAMCS, handling
    telemetry sending and telecommand receiving in a single-threaded manner.
    """

    COMMAND_HEADER_FORMAT = [
        {'name': 'start_word', 'type': 'U32'},
        {'name': 'opcode', 'type': YAMCSMDBGen.OPCODE_TYPE}
    ]
    START_WORD = 0xFEEDCAFE
    TM_HEADER_FORMAT = [
        {'name': 'PacketType', 'type': YAMCSMDBGen.PACKETTYPE_TYPE}, #PacketType to support events in the future
        {'name': 'PacketID', 'type': YAMCSMDBGen.PACKETID_TYPE} #PacketID to determine the format (id = index of TM refresh interval)
    ]
    TM_PACKETTYPE_VAL = YAMCSMDBGen.PACKETTYPE_TLM
    
    MAX_PACKET_SIZE = 1024

    def __init__(self, name, tcp_port: int, udp_port: int):
        """
        Initializes the YAMCS_link with a YAMCSContainer and TCP/UDP ports.

        Args:
            yamcs_container: The YAMCSContainer holding telemetry and telecommands.
            tcp_port: The TCP port to listen for commands from YAMCS.
            udp_port: The UDP port to send telemetry to YAMCS.
        """
        super().__init__(name)

        self.tcp_port = tcp_port
        self.udp_port = udp_port
        self.tcp_server_socket = None
        self.tcp_client_socket = None  # Socket connected to YAMCS
        self.udp_socket = None
        self.address = ('localhost', self.udp_port)  # Destination address
        self.input_list = []  # List of sockets to monitor with select()
        self.last_tm_send_time = {}  # Track last telemetry send time for each period
        self.command_header_serder = SerDer(self.COMMAND_HEADER_FORMAT) 
        self.tm_header_serder = SerDer(self.TM_HEADER_FORMAT)
        # Set up signal handling for graceful shutdown
        
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._start_tcp_server()

    def _signal_handler(self, sig, frame):
        """Handles signals for graceful shutdown."""
        logging.info(f"Received signal {sig}. Shutting down...")
        self.shutdown()
        sys.exit(0)
        
    def _start_tcp_server(self):
        """Starts the TCP server and prepares for telemetry sending."""
        try:
            self.tcp_server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_server_socket.setblocking(False)  # Non-blocking socket
            self.tcp_server_socket.bind(('localhost', self.tcp_port))
            self.tcp_server_socket.listen(1)
            logging.info(f"TCP server listening on port {self.tcp_port}")

            self.input_list = [self.tcp_server_socket]  # Start monitoring the server socket
            self.running = True

            logging.info("YAMCS_link started. Press Ctrl+C to shutdown.")

        except Exception as e:
            logging.error(f"Error starting YAMCS_link: {e}")
            self.shutdown()
            sys.exit(1)

    def generate_mdb(self, output_dir: str, name_mdb: str, version: str):
        """
        Generates the YAMCS mission database CSV files.

        Args:
            output_dir: The directory to save the generated CSV files.
            name_mdb: The name of the mission database.
            version: The version of the mission database.
        """
        self.update_index()

        try:
            mdb_generator = YAMCSMDBGen(name_mdb, version, output_dir)

            # Add enums, aggregates, and arrays types
            for enum_name, values in self.get_enums().items():
                mdb_generator.addEnumType(enum_name, self.ENUM_REPR_TYPE, values)

            # Add TM packets
            tm_def = self.get_tm_def()
            for i, (period, tm_list) in enumerate(tm_def.items()):
                packet = mdb_generator.TMPacket(name=f'tm-{self.yamcs_name}-{period}s', id=i, frequency=period)  #TODO: fix YAMCSMDBGen, it's not a frequency
                for tm in tm_list:
                    packet.addParam(tm['name'], tm['type'])
                mdb_generator.addTMTC(packet)

            # Add telecommands
            tc_def = self.get_tc_def()
            for opcode, tc in tc_def.items():
                command = mdb_generator.Command(name=tc['name'], opcode=opcode)
                for arg_name, arg_type in tc['args'].items():
                    command.addParam(arg_name, arg_type)
                mdb_generator.addTMTC(command)

            mdb_generator.validate()
            mdb_generator.generateCSVs()

            logging.info(f"Mission database generated successfully in {output_dir}")

        except Exception as e:
            logging.error(f"Error generating mission database: {e}")

    def service(self):
        """
        Handles telemetry sending and command receiving in a non-blocking manner.
        This method should be called repeatedly in a main loop.
        """
        try:
            # Use select() to monitor sockets for readability
            readable, _, _ = select.select(self.input_list, [], [], 0.1)  # 100ms timeout

            for sock in readable:
                if sock is self.tcp_server_socket:
                    # Accept new connection
                    conn, addr = self.tcp_server_socket.accept()
                    self.tcp_client_socket = conn
                    self.tcp_client_socket.setblocking(False)
                    self.input_list.append(self.tcp_client_socket)  # Monitor the new client socket
                    logging.info(f"Accepted connection from {addr}")
                elif sock is self.tcp_client_socket:
                    # Handle data from the client
                    data = self.tcp_client_socket.recv(self.MAX_PACKET_SIZE)
                    if data:
                        self.handle_command(data)
                    else:
                        # Connection closed
                        logging.info("Client disconnected.")
                        self.close_tcp_connection()

            # Send telemetry if TCP link is active
            if self.tcp_client_socket:
                self.send_telemetry()

        except Exception as e:
            logging.error(f"Error in service loop: {e}")
            self.close_tcp_connection()  # Ensure connection is closed on error

    def send_telemetry(self):
        """Sends telemetry data over UDP at the defined periods."""
        try:
            current_time = time.time()
            for i_period, period in enumerate(self.get_tm_periods()):
                if period not in self.last_tm_send_time:
                    self.last_tm_send_time[period] = 0

                if current_time - self.last_tm_send_time[period] >= period:
                    tm_data = self.get_tm_values(period)
                    if tm_data:
                        header_bytes = self.tm_header_serder.serialise([self.TM_PACKETTYPE_VAL, i_period])
                        self.udp_socket.sendto(header_bytes+tm_data, self.address)
                    self.last_tm_send_time[period] = current_time
        except Exception as e:
            logging.error(f"Telemetry sending error: {e}")

    def handle_command(self, data: bytes):
        """Handles incoming command data from the TCP connection."""
        
        #TODO: TCP is a streaming protocol, support segmentation at any point in a command

        header_size = self.command_header_serder.minsize
        if len(data) < header_size:
            logging.warning("Incomplete command received (too short). Dropping.")
            return

        try:
            logging.info(f"Received command: {data.hex()}")
            
            # Deserialize the command header using SerDer
            header = self.command_header_serder.deserialise(data)

            start_word = int(header['start_word'])
            if start_word != self.START_WORD:
                logging.warning(f"Invalid start word: 0x{start_word:X}. Dropping command.")
                return

            opcode = header['opcode']
            
            if(opcode >= len(self.commands)):
                logging.warning("Command opcode is out of bounds, ignoring command.")
                return

            if len(data) < header_size+self.commands[opcode]['serder'].minsize:
                logging.warning(f"Incomplete command received (expected length: {self.commands[opcode]['serder'].minsize}, received: {len(data)}). Dropping.")
                return

            # Call the telecommand in the YAMCS container
            result = self.call_tc(opcode, data[header_size:])
            logging.info(f"Command {opcode} (0x{opcode:X}) executed. Result: {result}")

        except Exception as e:
            logging.error(f"Command handling error: {e}")

    def close_tcp_connection(self):
        """Closes the TCP connection and cleans up."""
        if self.tcp_client_socket:
            self.input_list.remove(self.tcp_client_socket)
            self.tcp_client_socket.close()
            self.tcp_client_socket = None
            logging.info("TCP connection closed.")

    def shutdown(self):
        """Shuts down the TCP server and UDP socket."""
        self.close_tcp_connection()

        if self.tcp_server_socket:
            self.tcp_server_socket.close()
            logging.info("TCP server socket closed.")

        if self.udp_socket:
            self.udp_socket.close()
            logging.info("UDP socket closed.")

        logging.info("YAMCS_link shutdown complete.")


### Unit testing and usage #################################################################################

if __name__ == '__main__':
    # Example Usage
    from yamcs_userlib import YAMCSObject, telemetry, telecommand, U8, U16, F32
    from enum import Enum

    #Ports
    YAMCS_TM_PORT = 8001
    YAMCS_TC_PORT = 8000

    class MyEnum(Enum):
        VALUE1=1
        VALUE2=2

    class MyComponent(YAMCSObject):
        def __init__(self, name):
            YAMCSObject.__init__(self, name)

        @telemetry(1)
        def my_telemetry1(self) -> MyEnum:
            return MyEnum.VALUE1.value

        @telemetry(2)
        def my_telemetry2(self) -> U8:
            return 42

        @telecommand
        def my_command(self, arg1: U16, arg2: F32) -> None:
            print(f'MyComponent.my_command was invoked on {self.yamcs_name} with args {arg1}, {arg2}')

    # Initialize YAMCS link
    yamcs_link = YAMCS_link("my_link", tcp_port=YAMCS_TC_PORT, udp_port=YAMCS_TM_PORT) #Was creating the UDP ports in the receiving client
    my_component = MyComponent("component1")
    yamcs_link.register_yamcs_child(my_component)

    # Generate MDB
    yamcs_link.generate_mdb("mdb_output", "my_mdb", "1.0") #Needs to be before binding

    # Main loop
    try:
        while True:
            yamcs_link.service() #Run TM sending and TC handling
            time.sleep(0.1) #Small delay to prevent busy-waiting
    except KeyboardInterrupt:
        logging.info("Exiting main loop.")
    finally:
        #Close everything in this order
        yamcs_link.shutdown() #Ensure proper shutdown
