"""
Created on Mon Feb  3 2025

See YAMCSMDBGen description

@author: gmarchetx
"""

### Imports #########################################################################################

from typing import List, Tuple, Dict, Union, Any
import re

### Main class definition ##################################################################################

class YAMCSMDBGen:
    '''
    YAMCS mission database generator. Use this to construct in an intuitive way TM packets, commands, and all
    underlying data types and calibrations. 
    
    Note: does not support arrays in command arguments
    '''
    ### Exceptions #########################################################################################
    
    class NameConflictError(Exception):
        """Exception raised when a type is already defined."""
        def __init__(self, message):
            self.message = message
            super().__init__(self.message)
    
    class UndeclaredTypeError(Exception):
        """Exception raised when a type is used but not declared."""
        def __init__(self, message):
            self.message = message
            super().__init__(self.message)
            
    class UnknownNativeTypeError(Exception):
        """Exception raised when a native type is requested but does not exist in the mapping"""
        def __init__(self, message):
            self.message = message
            super().__init__(self.message)
            
    ### Public classes #####################################################################################
    
    # --- DataType classes
    
    class DataType:
        '''
        Contains information on a YAMCS TM or TC arg data type
        '''
        def __init__(self, typeName: str, engType: str, rawType: str, encoding: str, calibration: str = None):
            '''
            C.f. https://docs.yamcs.org/yamcs-server-manual/mdb/loaders/sheet/data-types/
            except for typeName which is one of the keys in TYPES_MAP
            '''
            self.name = typeName
            self.engType = engType
            self.rawType = rawType
            self.encoding = encoding
            self.calibration = calibration
            
        def __eq__(self, other): #To be able to detect name conflicts (which are same name but different data)
            if not isinstance(other, YAMCSMDBGen.DataType):
                return NotImplemented
            return (self.name == other.name and
                    self.engType == other.engType and
                    self.rawType == other.rawType and
                    self.encoding == other.encoding and
                    self.calibration == other.calibration)
            
    class PrimitiveDataType(DataType):
        '''
        Specialisation of datatype for primitive types which are basic types that a machine understands without prior definition
        '''
        def __init__(self, typeStr: str):
            '''
            
            '''
            typeTranslation = YAMCSMDBGen._translate_type(typeStr) #Translate type str to engineering type, raw type, and calibration type that YAMCS understands
            super().__init__(typeStr, typeTranslation[0], typeTranslation[1], typeTranslation[2])
            
    class EnumDataType(DataType):
        '''
        Specialisation of data type for enumerations. They have "calibration" (values).'''
        def __init__(self, typeName: str, typeStr: str):
            typeTranslation = YAMCSMDBGen._translate_type(typeStr) 
            super().__init__(typeName, 'enumerated', typeTranslation[1], typeTranslation[2], typeName) #Slightly different from primitive
            
    class ArrayDataType(DataType):
        '''
        Specialisation data type for arrays
        '''
        def __init__(self, typeName: str, typeStr: str):
            '''
            typeName is the name of the array type
            typeStr is the name of the type of each element (which could be another array type)
            '''
            super().__init__(typeName, typeStr+'[]', '', '') #YAMCS treats arrays as underlyintgType[] as engineering type. Size info is in the param name
            self.elType = typeStr #store the element type for validation of the database more conveniently
            
    class AggregateDataType(DataType):
        '''
        Specialisation data type for aggregates/structs
        '''
        def __init__(self, typeName, members: Dict[str, str]):
            '''
            typeName is the name of the aggregate type to create
            members is a dict mapping name of member to its type string. All of them will be processed
            '''
            super().__init__(typeName, '{'+' '.join([f'{t} {n};' for n, t in members.items()])+'}', '','') #Sort of C notation
            
            self.members = members  # Store members as a dictionary so that we can more easily make checks on them later on
            
    # --- Parameters classes 
    
    class Parameter:
        '''
        Holds information on parameters for TM packets or commands
        '''
        def __init__(self, name: str, typeName: str, default=None, min=None, max=None):
            '''
            name is the name of the parameter
            typename is the name of the type of the parameter
            default is the default value of the parameter (command arg only)
            min and max are the range allowed for the parameter (command arg only) 
            '''
            self.name = name
            self.typeName = typeName
            self.default = default
            self.min = min
            self.max = max
            
    class ArrayParameter(Parameter):
        '''
        Specialisation for array parameters
        '''
        def __init__(self, name: str, typeName: str, length: int):
            '''
            name is the name of the array parameter to create
            typeName is the name of the type of each element
            length is the length of the array
            '''
            super().__init__(name+f'[{length}]', typeName) #Array parameters have the length in their name
            
    # --- calibration classes 
    
    class Calib:
        '''
        Holds information on a calibration definition
        '''
        def __init__(self, typeName: str, kind: str, calibs1: List[str], calibs2: List[str]):
            '''
            typeName is the name of the calibration (which usually is the name of the associated type but doesn't have to)
            kind is the kind of calibration to create (c.F. https://docs.yamcs.org/yamcs-server-manual/mdb/loaders/sheet/calibration/)
            calibs and calibs 2 are lists, top to bottom, of the calibration values (c.f. same link)
            '''
            self.calibs1 = calibs1
            self.calibs2 = calibs2
            self.name = typeName
            self.kind = kind
            
        def __eq__(self, other): #To be able to check name conflicts more conveniently
            if not isinstance(other, YAMCSMDBGen.Calib):
                return NotImplemented
            return (self.name == other.name and
                    self.calibs1 == other.calibs1 and
                    self.calibs2 == other.calibs2 and
                    self.kind == other.kind)
            
    class EnumCalib(Calib):
        '''
        Specialisation calibration for enumerations
        '''
        def __init__(self, typeName: str, values: List[Union[str, Tuple[str, int]]]):
            '''
            typeName is the name of the enum to create
            values is a list of the string representation of the values in the enum, or a list of tuples (string, value)
            '''
            mapProvided = isinstance(values, dict)
            super().__init__(typeName, 
                             'enumeration', 
                             [v for v in values.values()] if mapProvided else [i for i in range(0,len(values))], 
                             [k for k in values.keys()] if mapProvided else values)
            
    # --- TMTC classes 
    
    class TMTCEntry:    
        '''
        Holds information on a command or a TM packet. Abstract class.
        '''    
        def __init__(self, name: str):
            self.params = []
            self.name = name
        
        def addArray(self, paramName: str, arrayName: str, arrayLength: int) -> None:
            '''
            Add an array parameter in this command or TM packet
            
            Parameters
            paramName: name of the parameter
            arrayName: name of the type of the array 
            arraylength: length of the array 
            '''
            self.params.append(YAMCSMDBGen.ArrayParameter(paramName, arrayName, arrayLength))
        
        def addParam(self, paramName: str, paramType: str, default=None, min=None, max=None) -> None:
            '''
            Add a regular (non array) parameter in this command (i.e. as argument) or TM packet
            
            Parameters
            paramName: name of the parameter
            paramType: name of the type of the parameter 
            default: default value of this parameter (command arg only)
            min and max: allowed range of this parameter (command arg only)
            '''
            self.params.append(YAMCSMDBGen.Parameter(paramName, paramType, default, min, max))
        
    class TMPacket(TMTCEntry):
        '''
        Specialisation for a TM packet
        '''
        def __init__(self, name: str, id: int, frequency=None):
            '''
            Parameters
            name: name of the packet
            id: id of the packet
            frequency: expected frequency for this packet (leave to None if no need to detect when packets have stopped refreshing)
            '''
            super().__init__(name)
            self.id = id
            self.freq = frequency

    class Command(TMTCEntry):
        '''
        Specialisation for a command
        '''
        def __init__(self, name: str, opcode: str):
            '''
            Parameters
            name: name of the command
            opcode: id of the packet for this command, which is the operation code
            '''
            super().__init__(name)
            self.opcode = opcode
    
    ### Public attributes ##################################################################################
    
    #Defines native or primitive types and their mapping to YAMCS data types (see DataTypes)
    TYPES_MAP = {
        "bool": ("uint", "uint", "8"), 
        "U8": ("uint", "uint", "8"),
        "U16": ("uint", "uint", "16"),
        "U32": ("uint", "uint", "32"),
        "U64": ("uint", "uint", "64"),
        "I8": ("int", "int", "8"),
        "I16": ("int", "int", "16"),
        "I32": ("int", "int", "32"),
        "I64": ("int", "int", "64"),
        "F32": ("float", "float", "32"),
        "F64": ("float", "float", "64"),
        r"string(\d+)": ("string","string","8*{}") #This one has a regex pattern and a formula around the captured value
    }
    
    #In TYPES_MAP, which type those variables are represented by. 
    #Required to describe the common part between a TM packet and an event packet since they go through the same data stream and preprocessor 
    #TODO: factorise into a dict instead
    OPCODE_TYPE = 'U32'
    PACKETID_TYPE = 'U32'
    PACKETTYPE_TYPE = 'U32'
    #The value of the packet type for TM packets. Required to write in the mission database which packets should be captured
    PACKETTYPE_TLM = 1
    #Same for events (even if this value is not used here, this centralises changes as it is used by yamcs_link.py). TODO: turn this into a dict
    PACKETTYPE_EVENT = 2
    
    #YAMCS doesn't support certain characters in parameter names etc. Use this map to make replacements in all names.
    #Currently cannot include [ ] { } ;
    NAME_REPLACE_MAP = {
        '.': '_' #YAMCS does not allow . in parameter names
    }
    
    ### Public methods #####################################################################################

    def __init__(self, name: str, version: str, directory: str):
        '''
        Parameters
        name of the mission database to be created, will be written in the filename and will prefix all exposed commands and TM
        as /name/
        version: version of the database (user parameter)
        directory: path of the output directory for the generated CSVs.
        '''
        self.name = name
        self.version = version
        self.directory = directory
        
        self.reset()
        
    def reset(self) -> None:
        '''
        Resets the generator i.e. empties all data previously filled in
        '''
        self.TMpackets = []
        self.commands = []
        self.dataTypes = []
        self.calibrations = []
        
        #Pre-fill with all native types but the string types (which require length information)
        for name, _  in YAMCSMDBGen.TYPES_MAP.items():
            if 'string' not in name:
                self.addPrimitiveType(name)
    
    def addTMTC(self, tmtc: TMTCEntry) -> None:
        '''
        Add either a command or a TM packet
        Parameters
        tmtc: the pre-filled command or TM packet
        '''
        if isinstance(tmtc, YAMCSMDBGen.Command):
            self.commands.append(tmtc)
        else:
            if isinstance(tmtc, YAMCSMDBGen.TMPacket):
                self.TMpackets.append(tmtc)
            else:
                raise Exception('Expecting TM packet or command')
        
    
    def addPrimitiveType(self, paramType: str) -> None:
        '''
        Add a primitive type (used primarily in reset() since all primitives are loaded at init())
        Parameters
        paramType: name of the type of the parameter as a key in TYPES_MAP
        '''
        self.dataTypes.append(YAMCSMDBGen.PrimitiveDataType(paramType))
    
    def addEnumType(self, enumName: str, enumType: str, values: List[Union[str, Tuple[str, int]]]) -> None:
        '''
        Add an enumeration type to the declared data types
        Parameters
        enumName: given name of the enumeration type
        enumType: name of the type of the enumeration i.E its representation type in the primitive types
        values: either a list of string represetnations (in which case their order will dictate the corresponding values) or list of tuple (string repr, value)
        '''
        self.dataTypes.append(YAMCSMDBGen.EnumDataType(enumName, enumType))            
        self.calibrations.append(YAMCSMDBGen.EnumCalib(enumName, values)) #Calibration names for enums are the same as the type name so no conflict can occur here
    
    def addArrayType(self, arrayName: str, membersType: str) -> None:
        '''
        Add an array type to the declared data types
        Parameters
        arrayName: name of the array type
        membersType: name of the type of all members in this array
        '''
        self.dataTypes.append(YAMCSMDBGen.ArrayDataType(arrayName, membersType))
    
    def addAggregateType(self, aggName: str, members: Dict[str, str]) -> None:
        '''
        Add an aggregate type to the declared data types
        Parameters
        aggName: aggregate type name
        members: Dictionary of {name: type string} where type string can be any name of type in the declared types
        '''
        self.dataTypes.append(YAMCSMDBGen.AggregateDataType(aggName, members))
        
    def validate(self) -> None:
        '''
        Validate the generator has been filled in properly:
        - check all referenced types exist in the types declaration
        - check all name conflicts
        - replace invalid characters
        '''
        # Check for type declarations
        for tmtc in self.TMpackets + self.commands:
            for param in tmtc.params:
                if not self._isTypeDeclared(param.typeName):
                    raise YAMCSMDBGen.UndeclaredTypeError(f"TMTC object '{tmtc.name}' contains parameter '{param.name}' with undeclared type '{param.typeName}'")

        # Check referenced types in qualified names
        for dt in self.dataTypes:
            if isinstance(dt, YAMCSMDBGen.ArrayDataType):
                if not self._isTypeDeclared(dt.elType):  
                    raise YAMCSMDBGen.UndeclaredTypeError(f"Array member type '{dt.elType}' for array type {dt.name} not found in existing data types")
            elif isinstance(dt, YAMCSMDBGen.AggregateDataType):
                for member_name, member_type in dt.members.items():
                    if not self._isTypeDeclared(member_type):
                        raise YAMCSMDBGen.UndeclaredTypeError(f"Member type '{member_type}' for member '{member_name}' in aggregate type {dt.name} not found in existing data types")
            
        # Check for name conflicts within each category
        def check_conflicts(items: List[Any], category_name: str) -> None:
            '''
            Helper function used to check for name conflicts in all types of containers filled in for this generator
            Parameters
            items: list of structures which have a name attribute
            category_name: used only for exception messages
            '''
            names = set()
            for item in items:
                if item.name in names:
                    raise YAMCSMDBGen.NameConflictError(f"Name conflict in {category_name}: '{item.name}' is used multiple times")
                names.add(item.name)
        
        check_conflicts(self.dataTypes, "datatypes")
        check_conflicts(self.TMpackets, "TM packets")
        check_conflicts(self.commands, "commands")
        check_conflicts(self.calibrations, "calibrations")

        # Check for parameter name conflicts within packets
        for packet in self.TMpackets:
            check_conflicts(packet.params, f"parameters of TM packet '{packet.name}'")

        # Check for parameter name conflicts within commands
        for command in self.commands:
            check_conflicts(command.params, f"parameters of command '{command.name}'")
        
        # Replace invalid characters (TODO: move to another function as this is not validating something)
        
        def _replace_invalid_chars_in_object(obj: Any) -> Any:
            '''
            Replaces invalid characters by predefined replacement recursively
            Parameters
            obj: any object
            '''
            if isinstance(obj, str):
                for old_char, new_char in YAMCSMDBGen.NAME_REPLACE_MAP.items():
                    obj = obj.replace(old_char, new_char)
                return obj
            elif isinstance(obj, list):
                return [_replace_invalid_chars_in_object(item) for item in obj]
            elif hasattr(obj, '__dict__'):
                for attr, value in vars(obj).items():
                    setattr(obj, attr, _replace_invalid_chars_in_object(value))
            return obj
        
        self.TMpackets = _replace_invalid_chars_in_object(self.TMpackets)
        self.commands = _replace_invalid_chars_in_object(self.commands)
        self.dataTypes = _replace_invalid_chars_in_object(self.dataTypes)
        self.calibrations = _replace_invalid_chars_in_object(self.calibrations)

    def generateCSVs(self) -> None:
        '''
        Generates the mission databases as specified in the constructor and using information previously filled in
        More details here:https://docs.yamcs.org/yamcs-server-manual/mdb/loaders/sheet/
        
        '''
        #Validate all data before writing it
        self.validate()
        
        #Headers for each worksheet, i.e. information which is written once at the beginning of each file
        #Used for example to define an abstract packet that contains packet type and packet Id, which are only derived
        #if packet type is correct
        headers = {
            "General": "format version,name,document version",
            "DataTypes": "type name,eng type,raw type,encoding,eng unit,calibration,description",
            "Containers": "container name,parent,condition,flags,entry,position,size in bits,expected interval,description\n"+
                          "PKT,,,,,,,\n"+
                          ",,,,PacketType,0,,\n"+
                          ",,,,PacketID,0,,\n",
            "Parameters": "parameter name,data type,description,namespace:MDB:OPS Name\n"
                          f"PacketType,{YAMCSMDBGen.PACKETTYPE_TYPE},,\n"+
                          f"PacketID,{YAMCSMDBGen.PACKETID_TYPE},,", 
            "Calibration": "calibrator name,type,calib1,calib2",
            "Commands": "command name,parent,argument assignment,flags,argument name,position,data type,default value,range low,range high,description"
        }
        
        #Templates for lines that are written for each object described in the keys. Some templates are different whether it's the first line for that entry or the other lines.
        templates = {
            "General": "7.1,{name},{version}",
            "DataTypes_type": "{name},{engType},{rawType},{encoding},,{calibration},",
            #Specialises for the correct packet type and for a given packet ID, offset in bits for things that are ignored in the abstract packet, then values in these that should match to apply this packet interpretation
            "Containers_packet": "{packetName},"+
                                 f"PKT:{int(YAMCSMDBGen.TYPES_MAP[YAMCSMDBGen.PACKETTYPE_TYPE][2])+int(YAMCSMDBGen.TYPES_MAP[YAMCSMDBGen.PACKETID_TYPE][2])}"+ 
                                 f",&(PacketType=={YAMCSMDBGen.PACKETTYPE_TLM}"+
                                 ";PacketID=={packetID}),,,,,{freq}",
            "Containers_param": ",,,,{name},0,,,",
            "Parameters_param": "{name},{type},,",
            "Calibration_start": "{name},{kind},{calib1},{calib2}",
            "Calibration_val": ",,{calib1},{calib2}",
            #Include the type of the opcode which is always the same
            "Commands_abstractCommand": "COMMAND,,,A,,,,,,,\n"+
                                        f",,,,OpCode,0,{YAMCSMDBGen.OPCODE_TYPE},,,,", 
            "Commands_command": "{name},COMMAND,OpCode={opcode},,,,,,,,",
            "Commands_arg": ",,,,{name},0,{type},{default},{min},{max},"
        }
        
        # General CSV has only one line after the header
        generalLines = [headers["General"], templates["General"].format(name=self.name, version=self.version)]
        
        # DataTypes CSV contains one line per type defined
        dataTypesLines = [headers["DataTypes"]]
        for dt in self.dataTypes:            
            dataTypesLines.append(templates["DataTypes_type"].format(
                name=dt.name,
                engType=dt.engType,
                rawType=dt.rawType,
                encoding=f'"{dt.encoding}"' if ',' in dt.encoding else dt.encoding, #if encoding contains a comma, escape it with ""
                calibration=dt.calibration or ""
            ))
        
        # Containers CSV contains lines one for each packet and one per each parameter
        #And Parameters CSV contains lines for each parameter used in Containers (to tell its type)
        containersLines = [headers["Containers"]]
        parametersLines = [headers["Parameters"]]
        for packet in self.TMpackets:
            #First line
            containersLines.append(templates["Containers_packet"].format(
                                                                            packetName=packet.name,
                                                                            packetID=packet.id,
                                                                            freq="" if packet.freq is None else packet.freq
                                                                        ))
            #All other lines
            for param in packet.params:
                containersLines.append(templates["Containers_param"].format(name=param.name))
                parametersLines.append(templates["Parameters_param"].format(name=param.name.split('[')[0], type=param.typeName)) #Parameters spreadsheet doesn't show array size, get rid of it
            containersLines.append("")  # Empty line after each packet
        
        # Calibration CSV contains lines for each enum and its values
        calibrationLines = [headers["Calibration"]]
        for calib in self.calibrations:
            #Write the first line
            calibrationLines.append(templates["Calibration_start"].format(
                name=calib.name,
                kind=calib.kind,
                calib1=calib.calibs1[0],
                calib2=calib.calibs2[0]
            ))
            
            #All other lines
            for i, (calib1, calib2) in enumerate(zip(calib.calibs1, calib.calibs2)):
                if i == 0:
                    continue  # First item already written using the different template line
                
                calibrationLines.append(templates["Calibration_val"].format(calib1=calib1, calib2=calib2))
            
            calibrationLines.append("")# Empty line after each enum
            
        # Commands CSV contains lines for each command and its arguments
        commandsLines=[headers["Commands"]]
        commandsLines.append(templates["Commands_abstractCommand"])
        commandsLines.append("")  # Empty line before the other commands
        for command in self.commands:
            commandsLines.append(templates["Commands_command"].format(name=command.name, opcode=command.opcode))
            for arg in command.params:
                commandsLines.append(templates["Commands_arg"].format(
                    name=arg.name,
                    type=arg.typeName,
                    default = "" if arg.default is None else arg.default,
                    min="" if arg.min is None else arg.min,
                    max="" if arg.max is None else arg.max,
                ))
            commandsLines.append("")  # Empty line after each command
        
        #Compile all lines and group them by worksheets
        sheetsLines_map={
            'General':generalLines,
            'DataTypes':dataTypesLines,
            'Containers':containersLines,
            "Parameters": parametersLines,
            'Calibration':calibrationLines,
            'Commands':commandsLines,
        }
        
        #Write the CSVs worksheet by worksheet in separate files folllowing the workbook_worksheet.csv format
        for sheet_name, lines in sheetsLines_map.items():
            filename = f"{self.directory}/{self.name}_{sheet_name}.csv"
            with open(filename, 'w', newline='') as file:
                for line in lines:
                    file.write(line + '\n')
                    
    ### Private methods #####################################################################################
     
    @staticmethod
    def _translate_type(t: str) -> Tuple[str, str, str]:
        '''
        Translates a primitive type into its YAMCS datatype description using TYPES_MAP
        Mainly contains logic for when the type is stringX where X is the length because it requires some regex
        
        Parameters:
        t: type string (should be a key in TYPES_MAP)
        
        Returns:
        tuple of engineering type, raw type, calibration (c.f. https://docs.yamcs.org/yamcs-server-manual/mdb/loaders/sheet/data-types/)
        '''
        if t in YAMCSMDBGen.TYPES_MAP:
            return YAMCSMDBGen.TYPES_MAP[t]
        
        #Allow the use of regex match and capture in TYPES_MAP
        for pattern, type_info in YAMCSMDBGen.TYPES_MAP.items():
            #If the key contains a valid regex pattern
            match = re.match(f"^{pattern}$", t)
            if match:
                groups = match.groups()
                if groups:
                    #Return a tuple of the fields in the values of TYPES_MAP
                    return tuple(
                        #if the considered field is number*{} write the field with the result of the calc, otherwise write the field verbatim
                        str(int(field.split('*')[0]) * int(groups[0])) if re.match(r'^\d+\*\{\}$', field) else field.format(*groups)
                        for field in type_info
                    )
                return type_info
        
        raise YAMCSMDBGen.UnknownNativeTypeError("Native type is not supported")      
       
    def _isTypeDeclared(self, typeName: str) -> bool:
        '''
        Returns true if the type has already been added as a datatype
        
        Parameters
        typeName: name of the type to analyse
        
        Returns:
        True if it has been declared previously
        '''
        #Ignores potential array notation to focus on the array name
        potentialBracketPos = typeName.rfind('[')
        if(potentialBracketPos != -1):
            baseName=typeName[:potentialBracketPos]
        else:
            baseName = typeName
        return any(dt.name == baseName for dt in self.dataTypes)
                    
### TESTING ################################################################################################################

if __name__ == "__main__":
    gen = YAMCSMDBGen("testMDB", "1.0", ".")
    
    gen.addEnumType('enum1', 'U8', {"VAL1":1,"VAL2":2,"VAL3":3})
    gen.addEnumType('enum2', 'U8', ['VALA', 'VALB', 'VALC'])
    #gen.addEnumType('enum1', 'uint8', [(1, 'VAL1'), (2, 'VAL2'), (3, 'VAL3')]) #Tests a 100% duplicate
    #gen.addEnumType('enum1', 'uint8', [(0, 'VAL1'), (2, 'VAL2'), (3, 'VAL3')]) #Tests a name conflict
    gen.addAggregateType('agg1', {'uint16param': 'U16', 'floatParam': 'F32', 'enum1param':'enum1'})
    gen.addArrayType('array1', 'F64')
    gen.addArrayType('array2', 'enum1')
    gen.addPrimitiveType('string40')
    #gen.addArrayType('array3', 'absentType') #Tests absent type (level 2)

    pkt1 = YAMCSMDBGen.TMPacket("testPacket1", 0, 1)
    pkt1.addParam('enumParam1', 'enum1')
    pkt1.addParam('enumParam2', 'enum2')
    pkt1.addParam('aggParam1', 'agg1')
    pkt1.addArray('arrayParam1', 'array1', 10)
    #pkt1.addParam('prergim1', 'stzqefr$')  #about this
    gen.addTMTC(pkt1) # Error: How come it doesn't complain?
    
    pkt2 = YAMCSMDBGen.TMPacket("testPacket2", 1, 2)
    pkt2.addParam('prim1', 'U8')
    gen.addTMTC(pkt2)

    cmd1 = YAMCSMDBGen.Command("testCmd1", 0)
    cmd1.addParam('prim3', 'I32', default=0, min=0, max=10)
    cmd1.addParam('str1', 'string40')
    #cmd1.addEnum('enumParam4', 'absentType') #Tests absent type (level 1)
    gen.addTMTC(cmd1)

    gen.generateCSVs()