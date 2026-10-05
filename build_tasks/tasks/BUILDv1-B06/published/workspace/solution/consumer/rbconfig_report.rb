require 'json'
require 'rbconfig'

out = {
  'ruby' => RbConfig.ruby,
  'prefix' => RbConfig::CONFIG['prefix'],
  'bindir' => RbConfig::CONFIG['bindir'],
  'rubylibdir' => RbConfig::CONFIG['rubylibdir'],
  'archdir' => RbConfig::CONFIG['archdir'],
  'ruby_version' => RUBY_VERSION,
  'patchlevel' => RUBY_PATCHLEVEL,
  'extensions' => Dir.glob(File.join(RbConfig::CONFIG['archdir'], '**', '*.so')).sort,
}
File.write(ARGV[0], JSON.pretty_generate(out))
