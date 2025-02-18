# -*- coding: utf-8 -*-
"""
Module: utils.py

Description: Provides a class, SerDer, for serializing and deserializing data structures
into byte streams and back using the struct module. 

Author: gmarchetx
Created on: Thu Feb 13 16:46:35 2025
"""

### Imports ###################################################################################################

import struct
import re
from typing import Dict, List, Any

### Public class definitions ###################################################################################

class SerDer:
    #Converts standard type strings to their struct.pack formats.
    #The standard type strings are driven by the YAMCS mission database generator (driven by Fprime)
    PACK_FORMATS = {
        'U8': 'B',
        'U16': 'H',
        'U32': 'I',
        'I8': 'b',
        'I16': 'h',
        'I32': 'i',
        'F32': 'f',
        'F64': 'd'
    }
    
    STRING_TYPE_REGEX = re.compile(r"string(\d+)")
    
    def __init__(self, fields: List[Dict[str, str]]):
        """
        Initializes a SerDer object with the specified fields.

        Args:
            fields (list): A list of dictionaries, where each dictionary describes a field to be
                           serialized/deserialized.  Each dictionary must contain 'name' (string)
                           and 'type' (string) keys.  The 'type' key must correspond to a valid
                           entry in the PACK_FORMATS dictionary.

        Raises:
            KeyError: If a field's 'type' is not found in PACK_FORMATS.

        Example:
            fields = [{'name': 'id', 'type': 'U16'}, {'name': 'temperature', 'type': 'F32'}]
        """
        self.fields = fields
        self.format = '>'  # Big-endian
        
        self.string_lengths = {} #stores the fixed size string lengths by type name as it's more convenient for ser/der
        for field in self.fields:
            field_type = field['type']
            match = self.STRING_TYPE_REGEX.match(field_type) #detects if the current field is a fixed size string
            #if it's a basic type, just look it up
            if field_type in self.PACK_FORMATS:
                self.format += self.PACK_FORMATS[field_type]
            #if it really is a fixed size string, memorise its length and add this special format to the aggregated format string
            elif match: 
                length = int(match.group(1))
                self.format += f"{length}s"
                self.string_lengths[field['name']] = length
            else:
                raise KeyError(f"Unsupported type: {field_type}")
        
        #Calculate the serialised size
        self.minsize = struct.calcsize(self.format) 

    def serialise(self, values: List[Any]) -> bytes:
        """
        Serializes a list of values into a byte stream.

        Args:
            values (list): A list of values to be serialized. The order of values must
                           match the order of fields defined during initialization.

        Returns:
            bytes: A byte stream representing the serialized data.

        Raises:
            struct.error: If the provided values do not match the expected format.
        """
        processed_values = []
        
        #Raise an exception if self.fields and values don't have the same sizes
        if(len(self.fields) != len(values)):
            raise ValueError("The number of fields must match the number of values to serialize (Got {len(values)} vs {len(self.fields)})")
        
        for field, value in zip(self.fields, values):
            #If it's a basic type, just take the value as-is
            if field['type'] in self.PACK_FORMATS:
                processed_values.append(value)
            #after init, if it's not in PACK_FORMATS it is a fixed size string
            else: 
                #Check value type passed as arg
                if not isinstance(value, str):
                    raise TypeError(f"String field {field['name']} must be a string.")

                #Since value is indeed a str, encode it to bytes
                str_bytes = value.encode('utf-8') 

                #Check there is enough space in the buffer to add a termination char
                length = self.string_lengths[field['name']]
                if len(str_bytes) >= length:
                    raise ValueError(f"String {field['name']} exceeds max length {length-1}.")

                #Append a fixed length of bytes padded with zeros
                processed_values.append(str_bytes.ljust(length, b'\0'))
                
        return struct.pack(self.format, *processed_values)

    def deserialise(self, byte_stream: bytes, exact_length=False) -> Dict[str, Any]:
        """
        Deserializes a byte stream into a dictionary of field names and values.

        Args:
            byte_stream (bytes): The byte stream to be deserialized.
            exact_length (bool, optional): If True, the byte stream must have exactly the
                                            expected size. If False, the byte stream can be
                                            longer than the expected size, and only the
                                            required portion will be deserialized. Defaults to False.

        Returns:
            dict: A dictionary where keys are field names and values are the deserialized
                  values from the byte stream.

        Raises:
            struct.error: If the byte stream does not match the expected format or is too short.
        """
        #Use the internal format to easily decode the byte stream into the expected fields
        unpacked = struct.unpack(self.format, byte_stream if exact_length else byte_stream[:self.minsize])
        
        result = {}
        for index, field in enumerate(self.fields):
            if field['name'] in self.string_lengths:
                #Remove padding and convert to str from bytes
                result[field['name']] = unpacked[index].split(b'\0', 1)[0].decode('utf-8')  
            else:
                result[field['name']] = unpacked[index]
            
        return result
    
### Unit testing and usage #################################################################################
    
if __name__ == "__main__":
    # Example usage:
    fields = [
        {'name': 'id', 'type': 'U16'},
        {'name': 'name', 'type': 'string16'},
        {'name': 'temperature', 'type': 'F32'},
        {'name': 'status', 'type': 'U8'}
    ]

    packer = SerDer(fields)
    data = [1234, "Test String", 23.5, 1]
    serialised = packer.serialise(data)
    print(f"Serialized: {[f'{byte:02x}' for byte in serialised]}")
    deserialised = packer.deserialise(serialised)
    print(f"Deserialized: {deserialised}")