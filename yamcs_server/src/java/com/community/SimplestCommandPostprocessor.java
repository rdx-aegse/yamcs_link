package com.community;

import java.nio.ByteBuffer;

import org.yamcs.YConfiguration;
import org.yamcs.commanding.PreparedCommand;
import org.yamcs.tctm.CommandPostprocessor;

public class SimplestCommandPostprocessor implements CommandPostprocessor {
    private static final byte[] HEADER = { (byte) 0xFE, (byte) 0xED, (byte) 0xCA, (byte) 0xFE };

    public SimplestCommandPostprocessor(String yamcsInstance) {
    }

    public SimplestCommandPostprocessor(String yamcsInstance, YConfiguration config) {
    }

    public byte[] process(PreparedCommand pc) {
        byte[] commandData = pc.getBinary();
        
        //Allocate a new byte buffer to hold the command data specified in mdb plus the header
        byte[] finalArray = new byte[HEADER.length + commandData.length];
        ByteBuffer buffer = ByteBuffer.wrap(finalArray);

        //Build the new byte buffer, i.e. same prepended with the header
        buffer.put(HEADER);
        buffer.put(commandData); //commandData contains the opcode, and yamcs_link knows the length of the arguments from the opcode

        //TODO: add checksum

        return finalArray;
    }
}
