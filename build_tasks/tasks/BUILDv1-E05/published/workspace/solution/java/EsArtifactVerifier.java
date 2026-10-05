import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.lang.reflect.Method;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;
import java.util.jar.Manifest;

/**
 * Independent verifier/consumer for the freshly built Elasticsearch :server JAR.
 *
 * Runs entirely outside the source tree and needs only a JDK.  It is a genuine
 * consumer of the produced artifact:
 *
 *   1. opens the JAR and asserts the frozen query-package classes are present
 *      (MatchQueryBuilder, AbstractQueryBuilder, QueryBuilder, BoolQueryBuilder)
 *      together with org.elasticsearch.Version;
 *   2. checks the CAFEBABE bytecode magic of each required class entry;
 *   3. reads Implementation-Version / Build-Jdk-Spec from MANIFEST.MF;
 *   4. loads the freshly built classes in an isolated URLClassLoader whose parent
 *      is the platform loader only (no leakage from the driver process) and
 *      invokes the real public API org.elasticsearch.Version.fromString and
 *      checks the returned value, checks that MatchQueryBuilder implements
 *      org.elasticsearch.index.query.QueryBuilder, and checks that
 *      MatchQueryBuilder was really loaded from the verified artifact.
 *
 * The second argument is a file holding the genuine :server dependency closure
 * (Lucene, log4j, libs/*, ...) resolved offline by Gradle; without it the server
 * classes cannot be initialised and the verifier reports that honestly instead
 * of pretending to have consumed them.
 *
 * This is a library-level API consumer.  It does NOT start an Elasticsearch
 * service (CORE profile scope).
 */
public final class EsArtifactVerifier {

    private static final String EXPECTED_VERSION = "8.17.6";

    private static final String[] REQUIRED = {
        "org/elasticsearch/index/query/MatchQueryBuilder.class",
        "org/elasticsearch/index/query/AbstractQueryBuilder.class",
        "org/elasticsearch/index/query/QueryBuilder.class",
        "org/elasticsearch/index/query/BoolQueryBuilder.class",
        "org/elasticsearch/Version.class",
    };

    public static void main(String[] args) throws Exception {
        if (args.length < 1) {
            System.err.println("usage: EsArtifactVerifier <server.jar> [consumer-classpath.txt]");
            System.exit(2);
        }
        Path jarPath = Path.of(args[0]);
        Path classpathFile = args.length > 1 ? Path.of(args[1]) : null;

        List<String> failures = new ArrayList<>();
        long entryCount = -1;
        String implementationVersion = null;
        String buildJdk = null;

        try (JarFile jar = new JarFile(jarPath.toFile())) {
            for (String required : REQUIRED) {
                JarEntry entry = jar.getJarEntry(required);
                if (entry == null) {
                    failures.add("missing entry: " + required);
                    continue;
                }
                try (InputStream stream = jar.getInputStream(entry)) {
                    byte[] magic = stream.readNBytes(4);
                    if (magic.length != 4
                            || magic[0] != (byte) 0xCA || magic[1] != (byte) 0xFE
                            || magic[2] != (byte) 0xBA || magic[3] != (byte) 0xBE) {
                        failures.add("invalid class bytecode: " + required);
                    }
                }
            }
            Manifest manifest = jar.getManifest();
            if (manifest == null) {
                failures.add("missing META-INF/MANIFEST.MF");
            } else {
                implementationVersion = manifest.getMainAttributes().getValue("Implementation-Version");
                buildJdk = manifest.getMainAttributes().getValue("Build-Jdk-Spec");
            }
            entryCount = jar.stream().count();
        } catch (IOException failure) {
            System.err.println("FAIL: cannot read jar " + jarPath + ": " + failure);
            System.exit(1);
        }

        System.out.println("server-jar=" + jarPath.toAbsolutePath());
        System.out.println("server-jar-bytes=" + Files.size(jarPath));
        System.out.println("server-jar-entry-count=" + entryCount);
        System.out.println("implementation-version=" + implementationVersion);
        System.out.println("build-jdk=" + buildJdk);

        if (implementationVersion == null) {
            System.out.println("WARN: no Implementation-Version manifest attribute");
        } else if (!EXPECTED_VERSION.equals(implementationVersion)) {
            failures.add("Implementation-Version mismatch: expected " + EXPECTED_VERSION
                    + " got " + implementationVersion);
        }

        // Real query-package API consumer over the freshly built classes.
        if (classpathFile == null || !Files.isReadable(classpathFile)) {
            failures.add("consumer dependency closure not supplied/readable: " + classpathFile);
        } else {
            String raw = Files.readString(classpathFile).trim();
            Set<URL> urls = new LinkedHashSet<>();
            urls.add(jarPath.toUri().toURL());
            for (String element : raw.split(File.pathSeparator)) {
                if (element.isBlank()) {
                    continue;
                }
                Path dependency = Path.of(element);
                if (Files.exists(dependency)) {
                    urls.add(dependency.toUri().toURL());
                }
            }
            System.out.println("consumer-classpath-urls=" + urls.size());
            URL[] array = urls.toArray(new URL[0]);
            try (URLClassLoader loader = new URLClassLoader(array, ClassLoader.getPlatformClassLoader())) {
                Class<?> versionClass = Class.forName("org.elasticsearch.Version", true, loader);
                Method fromString = versionClass.getMethod("fromString", String.class);
                Object version = fromString.invoke(null, EXPECTED_VERSION);
                String actual = String.valueOf(version);
                System.out.println("Version.fromString -> " + actual);
                if (!EXPECTED_VERSION.equals(actual)) {
                    failures.add("Version.fromString mismatch: expected " + EXPECTED_VERSION
                            + " got " + actual);
                }

                Class<?> queryBuilder = Class.forName(
                        "org.elasticsearch.index.query.QueryBuilder", true, loader);
                Class<?> matchQueryBuilder = Class.forName(
                        "org.elasticsearch.index.query.MatchQueryBuilder", true, loader);
                if (!queryBuilder.isAssignableFrom(matchQueryBuilder)) {
                    failures.add("MatchQueryBuilder does not implement QueryBuilder");
                }
                String loadedFrom = String.valueOf(
                        matchQueryBuilder.getProtectionDomain().getCodeSource().getLocation());
                System.out.println("MatchQueryBuilder-loaded-from=" + loadedFrom);
                if (!loadedFrom.contains(jarPath.getFileName().toString())) {
                    failures.add("MatchQueryBuilder was not loaded from the verified artifact: "
                            + loadedFrom);
                }
            } catch (Throwable failure) {
                failures.add("query-package API invocation failed: " + failure);
            }
        }

        if (!failures.isEmpty()) {
            for (String failure : failures) {
                System.err.println("FAIL: " + failure);
            }
            System.exit(1);
        }
        System.out.println("ES_SERVER_JAR_VERIFIED_OK");
    }
}
