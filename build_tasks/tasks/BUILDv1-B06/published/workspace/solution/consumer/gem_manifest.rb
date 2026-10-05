require 'json'
require 'rubygems'

out = Gem::Specification.map do |spec|
  {
    'name' => spec.name,
    'version' => spec.version.to_s,
    'default_gem' => spec.default_gem?,
    'full_gem_path' => spec.full_gem_path,
  }
end
File.write(ARGV[0], JSON.pretty_generate(out))
