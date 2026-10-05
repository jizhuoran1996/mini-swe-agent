Doctor incorrectly interprets the FIRST stderr line (Picked up JAVA_TOOL_OPTIONS:...) as Java's version. Genuine OpenJDK17+21 exist; the imposed ActiveProcessorCount/GC limits are required for bounded resource use. Parse the ACTUAL java/openjdk version line with regex across complete stdout+stderr, ignoring JAVA_TOOL_OPTIONS informational output; never fake version text or disable resource limits. Bind a genuine compatible JDK path if required by upstream. Real Maven3.8.6 wrapper and3.2.0 launcher are now fully prepared: sourceoverlaycopies exactofficialwrapper JAR after source extraction; hydrator restores its actual installed HOME/.m2/wrapper cache. Real Maven source deps /workspace/cache/maven are ready. Preserve complete -pl flink-core -am build+all declared official tests+realJava SDK serialization/negative consumer; no reduced tasks/testing. Return fullfiles.
Actualdoctorfailure:
{
  "info": {
    "archive": "/workspace/input/source.tar.gz",
    "java": "/usr/bin/java",
    "java_version": "Picked up JAVA_TOOL_OPTIONS: -XX:ActiveProcessorCount=4 -XX:ParallelGCThreads=2 -XX:ConcGCThreads=1",
    "maven_repo": "/workspace/cache/maven",
    "maven_repo_entries": 40,
    "profile": "core",
    "repo_candidates": [
      "/workspace/cache/maven",
      "/tmp/sbench-home/.m2/repository"
    ],
    "sha256": "82bf43c6fe515df0eab51081b32c97669edf22361ecf8a9861a7e41f242e5c1e",
    "task_id": "BUILDv1-E03",
    "top_level": [
      "flink-cb1e7b5571b06ebe3d79f57030663af3e83aefcd"
    ]
  },
  "missing": [
    "java version must be >= 17: Picked up JAVA_TOOL_OPTIONS: -XX:ActiveProcessorCount=4 -XX:ParallelGCThreads=2 -XX:ConcGCThreads=1"
  ],
  "ready": false
}
