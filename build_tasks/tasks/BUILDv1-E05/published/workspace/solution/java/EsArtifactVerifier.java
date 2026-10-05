import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;
import java.util.jar.Manifest;

/**
 * Independent verifier for the freshly built Elasticsearch :server JAR.
 *
 * Runs entirely outside the source tree and relies only on the JDK, so it is a
 * genuine consumer of the produced artifact (no source or classpath leakage).
 * CORE scope: this verifies the library artifact itself, it does not start a
 * full Elasticsearch service.
 */
public final class EsArtifactVerifier {

    private static final String[] REQUIRED = {
        "org/elasticsearch/index/query/MatchQueryBuilder.class",
        "org/elasticsearch/index/query/AbstractQueryBuilder.class",
        "org/elasticsearch/Version.class",
    };

    public static void main(String[] args) throws IOException {
        if (args.length < 1) {
            System.err.println("usage: EsArtifactVerifier <server.jar>");
            System.exit(2);
        }
        Path jarPath = Path.of(args[0]);
        List<String> failures = new ArrayList<>();
        long entries;
        try (JarFile jar = new JarFile(jarPath.toFile())) {
            for (String name : REQUIRED) {
                JarEntry entry = jar.getJarEntry(name);
                if (entry == null) {
                    failures.add("missing entry: " + name);
                    continue;
                }
                try (InputStream in = jar.getInputStream(entry)) {
                    byte[] magic = in.readNBytes(4);
                    if (magic.length != 4 || magic[0] != (byte) 0xCA || magic[1] != (byte) 0xFE
                            || magic[2] != (byte) 0xBA || magic[3] != (byte) 0xBE) {
                        failures.add("invalid class bytecode: " + name);
                    }
                }
            }
            Manifest manifest = jar.getManifest();
            if (manifest == null) {
                failures.add("missing MANIFEST.MF");
            } else {
                System.out.println("implementation-version="
                        + manifest.getMainAttributes().getValue("Implementation-Version"));
                System.out.println("build-jdk="
                        + manifest.getMainAttributes().getValue("Build-Jdk-Spec"));
            }
            entries = jar.stream().count();
        }
        System.out.println("server-jar=" + jarPath.toAbsolutePath());
        System.out.println("server-jar-entry-count=" + entries);
        if (!failures.isEmpty()) {
            failures.forEach(f -> System.err.println("FAIL: " + f));
            System.exit(1);
        }
        System.out.println("ES_SERVER_JAR_VERIFIED_OK");
    }
}
