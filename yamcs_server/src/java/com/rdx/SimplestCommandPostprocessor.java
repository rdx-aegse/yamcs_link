package com.rdx;

import java.nio.ByteBuffer;

import org.yamcs.YConfiguration;
import org.yamcs.commanding.PreparedCommand;
import org.yamcs.tctm.CommandPostprocessor;

public class SimplestCommandPostprocessor implements CommandPostprocessor {
    private static final byte[] HEADER = { (byte) 0xFE, (byte) 0xED, (byte) 0xCA, (byte) 0xFE };

    public SimplestCommandPostprocessor(String yamcsInstance) {
        // Constructor logic (if any)
    }

    public SimplestCommandPostprocessor(String yamcsInstance, YConfiguration config) {
        // Constructor logic (if any)
    }

    public byte[] process(PreparedCommand pc) {
        byte[] commandData = pc.getBinary();
        
        //Alternatively ByteBuffer buffer = ByteBuffer.allocate(HEADER.length + LENGTH_BYTES + length);
        byte[] finalArray = new byte[HEADER.length + commandData.length];
        ByteBuffer buffer = ByteBuffer.wrap(finalArray);

        buffer.put(HEADER);
        buffer.put(commandData);

        return finalArray;
    }
}
