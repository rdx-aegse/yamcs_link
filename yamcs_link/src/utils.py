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
        self.format = '>' + ''.join(self.PACK_FORMATS[field['type']] for field in self.fields)
        self.minsize = struct.calcsize(self.format)  # Calculate the expected size

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
        return struct.pack(self.format, *values)

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
        unpacked = struct.unpack(self.format, byte_stream if exact_length else byte_stream[:self.minsize])
        return {field['name']: value for field, value in zip(self.fields, unpacked)}
    
### Unit testing and usage #################################################################################
    
if __name__ == "__main__":
    # Usage example:
    fields = [
        {'name': 'id', 'type': 'U16'},
        {'name': 'temperature', 'type': 'F32'},
        {'name': 'status', 'type': 'U8'}
    ]
    
    packer = SerDer(fields)
    
    # Serialise
    data = [1234, 23.5, 1]
    serialised = packer.serialise(data)
    print('Serialised:')
    for byte in serialised:
        print(f"{byte:02x}", end=" ")
    
    
    # Deserialise
    deserialised = packer.deserialise(serialised)
    print(deserialised)