import java.nio.ByteBuffer;
import java.util.Arrays;

import org.apache.kafka.common.message.ApiVersionsRequestData;
import org.apache.kafka.common.protocol.ByteBufferAccessor;
import org.apache.kafka.common.protocol.ObjectSerializationCache;
import org.apache.kafka.common.serialization.StringDeserializer;
import org.apache.kafka.common.serialization.StringSerializer;

/**
 * Independent consumer for the freshly built kafka-clients jar.
 *
 * It exercises the generated protocol message code end to end on the wire:
 * size() -> write() -> read() -> write() and byte-for-byte comparison, for
 * protocol versions 0 (field-free), 3 and 4 (client software name/version),
 * plus a truncated-payload negative case and the string serde round trip.
 */
public final class KafkaProtocolRoundTrip {

    private static byte[] encode(ApiVersionsRequestData data, short version) {
        ObjectSerializationCache cache = new ObjectSerializationCache();
        int size = data.size(cache, version);
        ByteBuffer buffer = ByteBuffer.allocate(size);
        data.write(new ByteBufferAccessor(buffer), cache, version);
        buffer.flip();
        if (buffer.remaining() != size) {
            throw new AssertionError("v" + version + " wrote " + buffer.remaining() + " of " + size + " bytes");
        }
        byte[] payload = new byte[size];
        buffer.get(payload);
        return payload;
    }

    private static ApiVersionsRequestData decode(byte[] payload, short version) {
        ByteBuffer buffer = ByteBuffer.wrap(payload);
        ApiVersionsRequestData data = new ApiVersionsRequestData();
        data.read(new ByteBufferAccessor(buffer), version);
        return data;
    }

    public static void main(String[] args) {
        for (short version : new short[] {0, 3, 4}) {
            ApiVersionsRequestData data = new ApiVersionsRequestData();
            if (version >= 3) {
                data.setClientSoftwareName("kafka-roundtrip-consumer");
                data.setClientSoftwareVersion("3.9.1");
            }
            byte[] first = encode(data, version);
            ApiVersionsRequestData decoded = decode(first, version);
            byte[] second = encode(decoded, version);
            if (!Arrays.equals(first, second)) {
                throw new AssertionError("v" + version + " wire round trip mismatch");
            }
            if (version >= 3) {
                if (!"kafka-roundtrip-consumer".equals(decoded.clientSoftwareName())) {
                    throw new AssertionError("client software name lost in v" + version);
                }
                if (!"3.9.1".equals(decoded.clientSoftwareVersion())) {
                    throw new AssertionError("client software version lost in v" + version);
                }
            }
            System.out.println("roundtrip ok version=" + version + " bytes=" + first.length);
        }

        ApiVersionsRequestData data = new ApiVersionsRequestData();
        data.setClientSoftwareName("truncated");
        data.setClientSoftwareVersion("3.9.1");
        byte[] full = encode(data, (short) 3);
        byte[] truncated = Arrays.copyOf(full, Math.max(1, full.length - 3));
        boolean threw = false;
        try {
            decode(truncated, (short) 3);
        } catch (RuntimeException expected) {
            threw = true;
            System.out.println("negative case ok: " + expected.getClass().getName());
        }
        if (!threw) {
            throw new AssertionError("truncated payload decoded without error");
        }

        StringSerializer serializer = new StringSerializer();
        StringDeserializer deserializer = new StringDeserializer();
        byte[] keyBytes = serializer.serialize("round-trip", "event-key");
        if (!"event-key".equals(deserializer.deserialize("round-trip", keyBytes))) {
            throw new AssertionError("string serde round trip mismatch");
        }

        System.out.println("ROUNDTRIP_OK classes="
                + ApiVersionsRequestData.class.getProtectionDomain().getCodeSource().getLocation());
    }
}
