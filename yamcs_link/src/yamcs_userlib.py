# -*- coding: utf-8 -*-

"""
Module: yamcs_userlib.py

Description: Provides classes and decorators for defining telemetry and telecommands
within the YAMCS framework. Simplifies the creation and management of telemetry
and telecommand definitions using Python annotations, abstracting the underlying
data serialization and deserialization.

Author: gmarchetx

Created on: Thu Feb 13 16:46:35 2025

"""

### Imports ###################################################################################################

from typing import NewType, List, Any, Dict, Union
from enum import Enum
from collections import defaultdict
from utils import SerDer

### Public class definitions ###################################################################################

class EventSeverity(Enum):
    INFO = 0
    WATCH = 1
    WARNING = 2
    DISTRESS = 3
    CRITICAL = 4
    SEVERE = 5

class YAMCSObject:
    """
    Base class for any object that will declare telemetry and telecommands.
    Necessary to name all TM and TC
    """
    def __init__(self, name):
        """
        Initializes a YAMCSObject with a name.

        Args:
            name (str): The name of the YAMCS object. Only use letters, numbers and underscores
        """
        # TODO: enforce allowed characters
        self.yamcs_name = name

class YAMCSContainer(YAMCSObject):
    """
    Container for YAMCS objects (telemetry, telecommands).
    Can be used as an intermediate container to automatically name TM and TC in a hierarchical way, 
    to comply with the user's hierarchical design, 
    or to provide the interfaces to compile all TM/TC/Enum definitions, generate TM packets, and process TC byte streams
    """
    
    #Default representation type for enums, uses the type string convention in utils.SerDer
    ENUM_REPR_TYPE = 'U8'
    
    def __init__(self, name: str):
        """
        Initializes a YAMCSContainer with a name.

        Args:
            name (str): See YAMCSObject.__init__
        """
        super().__init__(name)
        self.parent = None
        self.children = []
        self.telemetry = {} #See _register_telemetry for schema
        self.commands = [] #See _register_command for schema

    def register_yamcs_child(self, child: YAMCSObject):
        """
        Registers a YAMCS object as a child of this container. Can be another container. 

        Args:
            child (YAMCSObject): The child YAMCS object.
        """
        child.parent = self #to send events up the chain
        self.children.append(child)

    def update_index(self):
        """
        Updates the internal telemetry and telecommand index which will be used when
        listing the tm/tc definitions, generating tm packets, and procecssing commands
        """
        self.telemetry = defaultdict(list)
        self.commands = []
        self._build_index(self, "") #Not a typo, build index starts with this YAMCSContainer as root

    def _build_index(self, obj: YAMCSObject, prefix: str):
        """
        Recursively builds the index of telemetry and telecommands. See update_index for reason
        
        Args:
            obj: YAMCSObject to analyse
            prefix: string which will be prepended to the full name of tm and tc, representing all parents
        """
        if isinstance(obj, YAMCSContainer):
            #If analysing a container, dive into it by recursion, adding to the full hierarchical name
            for child in obj.children:
                self._build_index(child, prefix + obj.yamcs_name + "-")
        else:
            #Find methods in the analysed object which are tagged with a telemetry or telecommand decorator 
            #and call the appropriate registration function
            registration_methods = {
                '_is_yamcs_TM': self._register_telemetry,
                '_is_yamcs_TC': self._register_command
            }
            for method_name in dir(obj):
                bound_method = getattr(obj, method_name)
                for attribute, registration_function in registration_methods.items():
                    if hasattr(bound_method, attribute):
                        fullname = prefix + obj.yamcs_name + "-" + method_name
                        registration_function(bound_method, fullname)

    def _register_telemetry(self, bound_method, fullname: str):
        """
        Retrieve the data left by a telemetry decorator in a bound method object
        and append the index entry to the self.telemetry dict

        Parameters
        ----------
        bound_method: bound method of the telemetry (obj.method)
        fullname : full name (including hierarchical trace) of telemetry parameter as seen in YAMCS

        Raises
        ------
        ValueError: duplicate telemetry full name
        """
        period = bound_method._refresh_period
        serder = SerDer([
            {
                'name': fullname, 
                #the serder is used to generate tm packets, it only uses basic types so replace the enum type with a basic type if applicable
                'type': self._get_potential_enum_repr_type(bound_method._yamcs_return_type)
            }
        ])

        # Check for duplicate telemetry names
        for tm in self.telemetry[period]:
            if tm['fullname'] == fullname:
                raise ValueError(f"Duplicate telemetry name: {fullname}")

        self.telemetry[period].append({
            'fullname': fullname,
            'bndmethod': bound_method,
            'serder': serder
        })

    def _register_command(self, bound_method, fullname: str):
        """
        Retrieve the data left by a telecommand decorator in a bound method object
        and append the index entry to the self.commands list

        Parameters
        ----------
        bound_method: bound method of the telemetry (obj.method)
        fullname : full name (including hierarchical trace) of telemetry parameter as seen in YAMCS

        Raises
        ------
        ValueError: duplicate telecommand full name
        """
        args = bound_method._yamcs_args
        fields = [
            {
                'name': arg_name, 
                #the serder is used to generate tm packets, it only uses basic types so replace the enum type with a basic type if applicable
                'type': self._get_potential_enum_repr_type(arg_type)
            } for arg_name, arg_type in args.items()
        ]
        serder = SerDer(fields)

        # Check for duplicate command names
        for cmd in self.commands:
            if cmd['fullname'] == fullname:
                raise ValueError(f"Duplicate command name: {fullname}")

        self.commands.append({
            'fullname': fullname,
            'bndmethod': bound_method,
            'serder': serder
        })
        
    def _get_potential_enum_repr_type(self, typ: str) -> str:
        """
        Unveil the representation type of an enum when applicable
        Any non-basic type will be interpreted as an enum
        
        Args:
            type: either part of SerDer.PACK_FORMATS o
            
        Return:
            new type str
        """
        #Assumes typ can only be an enum if it's not in PACK_FORMATS which is not ideal.
        #Enum may not be declared at this point in the current implementation, and in the current implementation self.get_enums() cannot be used yet
        return typ if typ in SerDer.PACK_FORMATS else self.ENUM_REPR_TYPE 
    
    def _cast_potential_enum_val(self, value: Union[int, float, Enum]) -> Union[int, float]:
        """
        Casts a value to its underlying representation if it is an enum.
        
        Args: 
            value: int, float, or of a type inheriting from Enum
            
        Return:
            new value
        """
        return value.value if isinstance(value, Enum) else value

    def get_enums(self) -> Dict[str, Dict[str, int]]:
        """
        Gets all enums used in telemetry and telecommands as dictionaries.
        
        Return:
            {enum name: {string_repr: value}}
        """
        enums = {}
        #Flattens the lists of TM across all periods to process them with the TC
        for tmtc in self.commands + sum(self.telemetry.values(), []): 
            enums.update(tmtc['bndmethod']._yamcs_enums)
        return enums

    def get_tm_def(self) -> Dict[float, List[Dict[str, Any]]]:
        """
        Get the definition of the compiled list of telemetry, with the aim to generate a YAMCS mission database from it
        
        Return:
            {period: [{'name':_, 'type':_}]}
        """
        tm_def = {}
        for period, tm_list in self.telemetry.items():
            tm_def[period] = [{'name': tm['fullname'], 'type': tm['bndmethod']._yamcs_return_type} for tm in tm_list]
        return tm_def
    
    def get_tm_values(self, period) -> List[int]:
        """
        Compile the values of all telemetry that was registered at the specified period interval into a single byte stream
        
        Args:
            period: targeted period in seconds
        
        Return:
            list of byte values
        """
        values = []
        for tm in self.telemetry[period]:
            serialized = tm['serder'].serialise([
                #SerDer will expect the enum represetnation type, so it is necessary to cast enums to that representation type
                self._cast_potential_enum_val(tm['bndmethod']())
            ])
            values.extend(serialized)
        return values
    
    def get_tm_periods(self) -> List[float]:
        """
        Get the list of different period intervals all the telemetry fall into after registration
        
        return
            list of float (seconds)
        """
        return self.telemetry.keys()

    def get_tc_def(self) -> List[Dict[str, Any]]:
        """
        Get the definition of the compiled list of telecommands, with the aim to generate a YAMCS mission database from it
        
        Return:
            [{'name': _, 'args': {'name': _, 'type': _, 'min':_, 'max':_}}]
        """
        tc_def = {}
        for i, cmd in enumerate(self.commands):
            tc_def[i] = {'name': cmd['fullname'], 'args': cmd['bndmethod']._yamcs_args}
        return tc_def

    def call_tc(self, opcode: int, arg_data: bytes) -> Any:
        """
        Call the method tagged as a telecommand which has been requested by its opcode ,
        using the passed arguments data as a byte stream
        
        Args:
            opcode: index of the command to be called in self.commands
            arg_data: bytes representing arguments to be deserialised and used when calling the method
            
        Return:
            return value of the targeted method (TODO: may be too much to allow any return type)
        """
        cmd = self.commands[opcode]
        # The deserialized data needs to be passed as keyword arguments
        deserialized_args = cmd['serder'].deserialise(arg_data, exact_length=True)
        return cmd['bndmethod'](**deserialized_args)
    
    def send_event(self, severity : EventSeverity, source: str, message : str):
        '''
        Send an event, either up the chain, or to YAMCS if at the top of the chain (is overriden by subclass YAMCS_link).
        Called by the @event decorator when a tagged method is called. 
        
        Args:
            severity: severity of the event picked among the values of EventSeverity that match the YAMCS severity definitions
            source: full path of the source object in the YAMCSContainers/YAMCSObjects hierarchy
            message: the message of the event (pre-formatted), as obtained from the methods tagged by @event decorators
        '''
        if(self.parent is not None):
            self.parent.send_event(severity, source, message)
        else:
            raise NotImplementedError("The root YAMCSContainer has to override send_event for events to be sent to YAMCS")
    
### Decorators and decorator helpers ########################################################################

def _extract_enums(typeList: List[Any]) -> Dict[str, Dict[str, Any]]:
    """
    Return all enums in a list of types as a dictionary {name: {string_repr: value}}
    
    Return:
        enums dict
    """
    enums = {}
    for arg_type in typeList:
        if isinstance(arg_type, type) and issubclass(arg_type, Enum):
            enums[arg_type.__name__] = {member.name: member.value for member in arg_type}
    return enums

# Decorator for TM
def telemetry(period=1):
    """
    Decorator to tag a YAMCSObject method as YAMCS telemetry.
    Usage: @telemetry() or @telemetry(1) or @telemetry(period=1) AND you must use type hints with the predefined types below. Return the telemetry value.
    
    Args:
        period: interval at which the telemetry will be declared to be acquired, in seconds (optional)
        
    Return:
        decorated method
    """
    def decorator(func):
        #Tag the function as telemetry
        func._is_yamcs_TM = True
        
        #Store information that a YAMCSContainer will eventually compile
        func._refresh_period = period
        return_type = func.__annotations__.get('return')
        if return_type is None:
            raise ValueError(f"Telemetry function {func.__name__} must have a return type annotation")
        func._yamcs_return_type = return_type.__name__  # Store the name of the return type
        func._yamcs_enums = _extract_enums([return_type])
        return func
    
    return decorator

# Decorator for TC
def telecommand(func):
    """
    Decorator to tag a YAMCSObject method as YAMCS telecommand
    Usage: @telecommand AND you must use type hints with the predefined types below
        
    Return:
        decorated method
    """
    #Tag the function as telecommand
    func._is_yamcs_TC = True
    #Store information that a YAMCSContainer will eventually compile
    func._yamcs_args = {k: v.__name__ for k, v in func.__annotations__.items() if k != 'return'}
    func._yamcs_enums = _extract_enums(func.__annotations__.values())
    return func

#decorator for events
def event(severity: EventSeverity):
    '''
    Decorator to tag a YAMCSObject method as a YAMCS event
    Usage: @event(EventSeverity.<VALUE>), then return the f-string of the message formatted with the method's arguments
    
    Args:
        severity of the event
    '''
    # Decorator factory: Creates a decorator with specified severity
    def decorator(func):
        # Actual decorator: replaces the function with the wrapper
        def wrapper(self, *args, **kwargs):
            #Gets the message and sends the event applying the specified severity
            message = func(self, *args, **kwargs)
            self.parent.send_event(severity, self.yamcs_name, message)
            return message
        return wrapper
    return decorator

### Type definitions for type hints of decorated methods #################################################

# Predefined Types to be used in the type hints of any method decorated with @telemetry or @telecommand
#The type strings match those in SerDer.PACK_FORMATS, and map those to native python types
#Reason: control the lengths of serialisations while the native types have variable storage type
U8 = NewType('U8', int)
U16 = NewType('U16', int)
U32 = NewType('U32', int)
I8 = NewType('I8', int)
I16 = NewType('I16', int)
I32 = NewType('I32', int)
F32 = NewType('F32', float)
F64 = NewType('F64', float)

### Unit testing and usage #################################################################################

if __name__ == '__main__':
    # Example usage
    class MyEnum(Enum):
        VALUE1 = 1
        VALUE2 = 2

    class MyEnum2(Enum):
        VALUE3 = 3
        VALUE4 = 4

    class MyComponent(YAMCSObject):
        def __init__(self, name):
            YAMCSObject.__init__(self, name)

        @telemetry(1)
        def my_telemetry1(self) -> MyEnum:
            return MyEnum.VALUE1

        @telemetry(2)
        def my_telemetry2(self) -> MyEnum:
            return MyEnum.VALUE2

        @telecommand
        def my_command(self, arg1: U16, arg2: F32, arg3: MyEnum2) -> None:
            print(f'MyComponent.my_command was invoked on {self.name} with args {arg1}, {arg2}, {arg3}')

    class AnotherComponent(YAMCSObject):
        def __init__(self, name):
            YAMCSObject.__init__(self, name)

        @telemetry(1)
        def my_telemetry1(self) -> U32:
            return 42

        @telemetry(3)
        def my_telemetry2(self) -> U32:
            return 42

    root = YAMCSContainer("")
    container = YAMCSContainer("container")
    component1 = MyComponent("component1")
    component2 = AnotherComponent("component2")
    component1b = MyComponent("component1b")

    root.register_yamcs_child(container)
    container.register_yamcs_child(component1)
    container.register_yamcs_child(component2)
    container.register_yamcs_child(component1b)

    root.update_index()

    # Demonstrate get_tm_def
    print("===Telemetry Definitions===")
    tm_def = root.get_tm_def()
    for period, tm_list in tm_def.items():
        print(f"Period: {period}")
        for tm in tm_list:
            print(f"  Name: {tm['name']}, Type: {tm['type']}")

    # Demonstrate get_tm_values
    print("\n===Telemetry Values===")
    for period in root.get_tm_periods():
        print(f"For period: {period}s, packet = {root.get_tm_values(period)}")  # Print the byte representation

    # Demonstrate get_tc_def
    print("\n===Telecommand Definitions===")
    tc_def = root.get_tc_def()
    for opcode, tc in tc_def.items():
        print(f"Opcode: {opcode}, Name: {tc['name']}, Args: {tc['args']}")

    # Demonstrate call_tc
    print("\n===Calling Telecommand===")
    # Find the opcode for 'EGSE-container-component1-my_command'
    target_command_name = 'EGSE-container-component1-my_command'
    target_opcode = None
    for opcode, tc in root.get_tc_def().items():
        if tc['name'] == target_command_name:
            target_opcode = opcode
            break

    if target_opcode is not None:
        # Arguments for the telecommand (must match the definition)
        arg1 = U16(1234)
        arg2 = F32(12.34)
        arg3 = MyEnum2.VALUE3

        # Construct the argument data as a byte stream (matching the SerDer format)
        # Note: The order must match the order in the telecommand definition
        tc = root.commands[target_opcode]  # Get the command definition
        # Pack arguments into a byte stream using SerDer
        arg_values = [arg1, arg2, arg3.value]  # Correct order and enum value
        arg_data = tc['serder'].serialise(arg_values)

        # Call the telecommand
        try:
            result = root.call_tc(target_opcode, arg_data)
            print(f"Telecommand '{target_command_name}' executed successfully.")
        except Exception as e:
            print(f"Error calling telecommand: {e}")
    else:
        print(f"Telecommand '{target_command_name}' not found.")

    print('\n===Enums:')
    for name, valuesMap in root.get_enums().items():
        print(f'---{name}: {valuesMap}')
