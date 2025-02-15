package com.rdx;

import java.util.concurrent.atomic.AtomicInteger;

import org.yamcs.TmPacket;
import org.yamcs.YConfiguration;
import org.yamcs.tctm.AbstractPacketPreprocessor;
import org.yamcs.utils.TimeEncoding;

public class SimplestPacketPreprocessor extends AbstractPacketPreprocessor {
    private AtomicInteger seqCount = new AtomicInteger();

    public SimplestPacketPreprocessor(String yamcsInstance) {
        super(yamcsInstance, YConfiguration.emptyConfig());
    }

    @Override
    // Our packets don't have any header but YAMCS wants a timestamp and sequence count.
    public TmPacket process(TmPacket packet) {
        // Generate a sequential sequence count
        packet.setSequenceCount(seqCount.getAndIncrement());

        // Use the wall clock time.
        packet.setGenerationTime(TimeEncoding.getWallclockTime());

        return packet;
    }
}
