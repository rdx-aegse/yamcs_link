package com.community;

import java.util.concurrent.atomic.AtomicInteger;

import org.yamcs.TmPacket;
import org.yamcs.YConfiguration;
import org.yamcs.tctm.AbstractPacketPreprocessor;
import org.yamcs.utils.TimeEncoding;

public class SimplestPacketPreprocessor extends AbstractPacketPreprocessor {
    //Every packet must have a unique sequence count to exist in the parameter archive
    private AtomicInteger seqCount = new AtomicInteger();

    public SimplestPacketPreprocessor(String yamcsInstance) {
        super(yamcsInstance, YConfiguration.emptyConfig());
    }

    @Override
    // Our packets don't have any header but YAMCS wants a timestamp and sequence count.
    public TmPacket process(TmPacket packet) {
        // Generate a sequential sequence count
        packet.setSequenceCount(seqCount.getAndIncrement());

        // Use the wall clock time for now, may extract it from the packets later
        packet.setGenerationTime(TimeEncoding.getWallclockTime());

        //TODO: add checksum check

        //Otherwise forward the packet as-is to the parsing specified in the mdb
        return packet;
    }
}
