package com.community;

import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import org.yamcs.AbstractYamcsService;
import org.yamcs.InitException;
import org.yamcs.Spec;
import org.yamcs.Spec.OptionType;
import org.yamcs.YConfiguration;
import org.yamcs.YamcsServer;
import org.yamcs.events.EventProducer;
import org.yamcs.events.EventProducerFactory;
import org.yamcs.protobuf.Event.EventSeverity;
import org.yamcs.time.TimeService;
import org.yamcs.yarch.Stream;
import org.yamcs.yarch.StreamSubscriber;
import org.yamcs.yarch.Tuple;
import org.yamcs.yarch.YarchDatabase;
import org.yamcs.yarch.YarchDatabaseInstance;
import org.yamcs.yarch.protobuf.Db.Event;
import static org.yamcs.StandardTupleDefinitions.GENTIME_COLUMN;
import static org.yamcs.StandardTupleDefinitions.TM_RECTIME_COLUMN;

public class SimplestEventDecodingService extends AbstractYamcsService implements StreamSubscriber {
    private Stream stream;
    private int nBytesSource;
    private int nBytesMsg;

    private String streamName;
    private EventProducer eventProducer;
    private TimeService timeService;

    private static final int PACKETTYPE = 2;
    private static final ByteOrder ENDIANNESS = ByteOrder.BIG_ENDIAN;
    private static final int N_BYTES_PACKETTYPE = 4;
    private static final int N_BYTES_PACKETID = 4;
    private static final int N_BYTES_SEVERITY = 1;

    @Override
    public Spec getSpec() {
        Spec spec = new Spec();
        spec.addOption("stream", OptionType.STRING);
        spec.addOption("nBytesSource", OptionType.INTEGER);
        spec.addOption("nBytesMsg", OptionType.INTEGER);
        return spec;
    }

    @Override
    public void init(String yamcsInstance, String serviceName, YConfiguration config) throws InitException {
        super.init(yamcsInstance, serviceName, config);
        streamName = config.getString("stream");
        nBytesSource = config.getInt("nBytesSource");
        nBytesMsg = config.getInt("nBytesMsg");
        eventProducer = EventProducerFactory.getEventProducer(yamcsInstance);
    }

    @Override
    protected void doStart() {
        YarchDatabaseInstance ydb = YarchDatabase.getInstance(yamcsInstance);
        stream = ydb.getStream(streamName);
        if (stream != null) {
            log.info("Subscribing to stream {}", streamName);
            stream.addSubscriber(this);
        }
        else {
            log.error("Stream {} not found", streamName);
            notifyFailed(new Exception("Stream not found"));
            return;
        }
        timeService = YamcsServer.getTimeService(yamcsInstance);
        notifyStarted();
    }

    @Override
    protected void doStop() {
        stream.removeSubscriber(this);
        notifyStopped();
    }

    @Override
    public void onTuple(Stream stream, Tuple t) {
        byte[] packet = (byte[]) t.getColumn("packet");
        ByteBuffer buffer = ByteBuffer.wrap(packet).order(ENDIANNESS);  

        if (buffer.remaining() < N_BYTES_PACKETTYPE) {
            log.warn("Packet too short to read packet type");
            return;
        }

        int packetTypeId = buffer.getInt();  
        if (packetTypeId == PACKETTYPE) {
            long rectime = (Long) t.getColumn(TM_RECTIME_COLUMN); 
            long gentime = (Long) t.getColumn(GENTIME_COLUMN); 
            try {
                processPacket(rectime, gentime, packet);
            } catch (Exception e) {
                log.warn("Failed to process event packet", e);
            }
        }
    }

    private void processPacket(long rectime, long gentime, byte[] packet) {
        // Calculate the expected minimum packet length
        int minPacketLength = N_BYTES_PACKETTYPE + N_BYTES_PACKETID + N_BYTES_SEVERITY + nBytesSource + nBytesMsg;

        ByteBuffer buffer = ByteBuffer.wrap(packet).order(ENDIANNESS);  

        // Check if the packet is long enough to contain all expected fields
        if (buffer.remaining() < minPacketLength) {
            log.warn("Packet too short. Expected at least {} bytes, but got {}", minPacketLength, buffer.remaining());
            return;
        }

        buffer.position(N_BYTES_PACKETTYPE + N_BYTES_PACKETID);
        int severity = buffer.get();
        String source = readString(buffer, nBytesSource);
        String message = readString(buffer, nBytesMsg);

        log.info("Event decoded - Severity: {}, Source: {}, Message: {}", severity, source, message);

        Event ev = Event.newBuilder()
                        .setGenerationTime(gentime)
                        .setReceptionTime(rectime)
                        .setSeqNumber(0)
                        .setSource(source)
                        .setSeverity(EventSeverity.forNumber(severity))
                        .setType("YAMCS_LINK")
                        .setMessage(message).build();
        eventProducer.sendEvent(ev);
    }

    private static String readString(ByteBuffer buf, int length) {
        byte[] bytes = new byte[length];
        buf.get(bytes);
        return new String(bytes, StandardCharsets.UTF_8).trim();
    }

    @Override
    public void streamClosed(Stream stream) {
        log.warn("Stream {} closed", stream.getName());
    }
}
