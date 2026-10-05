require 'json'
require 'zlib'
require 'digest'
require 'socket'
require 'tempfile'
require 'openssl'
require 'stringio'

raise 'RbConfig.ruby missing' unless RbConfig.ruby && File.exist?(RbConfig.ruby)
raise 'prefix does not look like install tree' unless RbConfig::CONFIG['prefix'].include?('install')

data = { 'name' => 'ruby', 'values' => [1, 2, 3], 'nested' => { 'ok' => true } }
json = JSON.generate(data)
raise 'json round trip failed' unless JSON.parse(json) == data
raise 'json C extension not loaded' unless defined?(JSON::Ext::Parser)

payload = 'hello ' * 1000
raise 'zlib round trip failed' unless Zlib::Inflate.inflate(Zlib::Deflate.deflate(payload)) == payload
raise 'zlib C extension not loaded' unless defined?(Zlib::Deflate)

raise 'digest mismatch' unless Digest::SHA256.hexdigest('abc') ==
  'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'

q = Queue.new
threads = 4.times.map do |i|
  Thread.new { 100.times { |j| q << (i * 1000 + j) } }
end
threads.each(&:join)
items = []
items << q.pop until q.empty?
raise 'thread count mismatch' unless items.size == 400
raise 'thread duplicate items' unless items.uniq.size == 400

Tempfile.create('consumer') do |f|
  f.write(json)
  f.flush
  f.rewind
  raise 'file read mismatch' unless JSON.parse(f.read) == data
end

s = 'hello world'
raise 'string upcase failed' unless s.upcase == 'HELLO WORLD'
raise 'string capitalize failed' unless s.split.map(&:capitalize).join(' ') == 'Hello World'

raise 'socket C extension not loaded' unless defined?(Socket)
raise 'openssl C extension not loaded' unless defined?(OpenSSL::Digest)

puts "CONSUMER_OK ruby=#{RUBY_VERSION} platform=#{RUBY_PLATFORM}"
