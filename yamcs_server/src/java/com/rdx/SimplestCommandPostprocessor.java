package com.rdx;

import java.nio.ByteBuffer;

import org.yamcs.YConfiguration;
import org.yamcs.commanding.PreparedCommand;
import org.yamcs.tctm.CommandPostprocessor;

public class SimplestCommandPostprocessor implements CommandPostprocessor {
    private static final byte[] HEADER = { (byte) 0xDE, (byte) 0xAD, (byte) 0xBE, (byte) 0xEF };
    private static final int LENGTH_BYTES = 2;

    public SimplestCommandPostprocessor(String yamcsInstance) {
        // Constructor logic (if any)
    }

    public SimplestCommandPostprocessor(String yamcsInstance, YConfiguration config) {
        // Constructor logic (if any)
    }

    public byte[] process(PreparedCommand pc) {
        byte[] commandData = pc.getBinary();
        
        int length = commandData.length;
        
        //Alternatively ByteBuffer buffer = ByteBuffer.allocate(HEADER.length + LENGTH_BYTES + length);
        byte[] finalArray = new byte[HEADER.length + LENGTH_BYTES + length];
        ByteBuffer buffer = ByteBuffer.wrap(finalArray);

        buffer.put(HEADER);
        buffer.putShort((short) length); // big-endian order
        buffer.put(commandData);

        return finalArray;
    }
}
