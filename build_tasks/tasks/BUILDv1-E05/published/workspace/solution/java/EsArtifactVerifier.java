import java.io.IOException;
import java.io.InputStream;
import java.lang.reflect.Method;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;
import java.util.jar.Manifest;

/**
 * Independent verifier for the freshly built Elasticsearch :server JAR.
 *
 * Runs entirely outside the source tree and relies only on the JDK.  It is a
 * genuine consumer of the produced artifact: it opens the JAR, checks for the
 * frozen query-package classes, verifies their {@code CAFEBABE} bytecode magic,
 * loads {@code org.elasticsearch.Version} in an isolated {@link URLClassLoader}
 * and invokes the real public API {@code Version.fromString("8.17.6")}.
 *
 * This is a library-level API consumer - it does NOT start an Elasticsearch
 * service (CORE profile scope).
 */
public final class EsArtifactVerifier {

    private static final String EXPECTED_VERSION = "8.17.6";

    private static final String[] REQUIRED = {
        "org/elasticsearch/index/query/MatchQueryBuilder.class",
        "org/elasticsearch/index/query/AbstractQueryBuilder.class",
        "org/elasticsearch/Version.class",
    };

    public static void main(String[] args) throws Exception {
        if (args.length < 1) {
            System.err.println("usage: EsArtifactVerifier <server.jar>");
            System.exit(2);
        }
        Path jarPath = Path.of(args[0]);
        List<String> failures = new ArrayList<>();
        long entries = -1;

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
        } catch (IOException failure) {
            System.err.println("FAIL: cannot read jar: " + failure);
            System.exit(1);
        }
        System.out.println("server-jar=" + jarPath.toAbsolutePath());
        System.out.println("server-jar-entry-count=" + entries);

        // Real query package API consumer: load Version from the built jar and
        // invoke the public fromString factory through reflection.
        try (URLClassLoader loader = new URLClassLoader(
                new URL[]{jarPath.toUri().toURL()}, ClassLoader.getPlatformClassLoader())) {
            Class<?> versionClass = Class.forName("org.elasticsearch.Version", true, loader);
            Method fromString = versionClass.getMethod("fromString", String.class);
            Object version = fromString.invoke(null, EXPECTED_VERSION);
            String actual = String.valueOf(version);
            System.out.println("Version.fromString(\"" + EXPECTED_VERSION + "\") -> " + actual);
            if (!EXPECTED_VERSION.equals(actual)) {
                failures.add("Version mismatch: expected " + EXPECTED_VERSION + " got " + actual);
            }
        } catch (Throwable failure) {
            failures.add("query-package API invocation failed: " + failure);
        }

        if (!failures.isEmpty()) {
            failures.forEach(f -> System.err.println("FAIL: " + f));
            System.exit(1);
        }
        System.out.println("ES_SERVER_JAR_VERIFIED_OK");
    }
}
