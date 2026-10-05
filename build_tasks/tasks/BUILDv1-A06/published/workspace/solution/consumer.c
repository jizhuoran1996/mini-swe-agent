#include <uv.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>

static int failures = 0;
#define CHECK(cond, msg) do { if (!(cond)) { fprintf(stderr, "FAIL: %s\n", msg); failures++; } } while (0)

static uv_loop_t *loop;
static uv_fs_t open_req, read_req, close_req;
static uv_file open_file = -1;
static char file_buf[256];
static ssize_t file_len = 0;

static uv_process_t child_req;
static uv_process_options_t child_opts;
static int child_exit_status = -1;

static uv_work_t work_req;
static int work_ran = 0;
static int after_work_ran = 0;

static uv_timer_t timer_req;
static int timer_fired = 0;

static uv_tcp_t server, client, peer;
static int echo_done = 0;

/* Forward declarations: libuv requires callbacks that are sometimes defined
 * after their first use (on_read is set from on_open; on_server_write is set
 * from on_server_read).  Real C functions, no macros or fake shims. */
static void on_read(uv_fs_t *req);
static void on_server_write(uv_write_t *req, int status);
static void on_client_write(uv_write_t *req, int status);

static void safe_close(uv_handle_t *h) { if (!uv_is_closing(h)) uv_close(h, NULL); }

static void on_open(uv_fs_t *req) {
    CHECK(req->result >= 0, "fs open");
    if (req->result < 0) return;
    open_file = req->result;
    uv_buf_t buf = uv_buf_init(file_buf, sizeof(file_buf));
    uv_fs_read(loop, &read_req, open_file, &buf, 1, -1, on_read);
}

static void on_read(uv_fs_t *req) {
    CHECK(req->result >= 0, "fs read");
    if (req->result > 0) file_len = req->result;
    uv_fs_close(loop, &close_req, open_file, NULL);
}

static void on_child_exit(uv_process_t *req, int64_t exit_status, int term_signal) {
    (void)term_signal;
    child_exit_status = (int)exit_status;
    uv_close((uv_handle_t *)req, NULL);
}

static void work_cb(uv_work_t *req) { (void)req; work_ran = 1; }
static void after_work_cb(uv_work_t *req, int status) { (void)req; CHECK(status == 0, "work status"); after_work_ran = 1; }

static void on_timer(uv_timer_t *handle) { timer_fired = 1; uv_close((uv_handle_t *)handle, NULL); }

static void on_stop_timer(uv_timer_t *handle) {
    safe_close((uv_handle_t *)&peer);
    safe_close((uv_handle_t *)&client);
    safe_close((uv_handle_t *)&server);
    uv_close((uv_handle_t *)handle, NULL);
}

static void alloc_cb(uv_handle_t *handle, size_t suggested, uv_buf_t *buf) {
    (void)handle;
    size_t n = suggested ? suggested : 1;
    buf->base = malloc(n);
    buf->len = n;
}

static void on_server_read(uv_stream_t *stream, ssize_t nread, const uv_buf_t *buf) {
    if (nread <= 0) { if (buf->base) free(buf->base); return; }
    uv_write_t *wreq = malloc(sizeof(*wreq));
    char *data = malloc((size_t)nread);
    memcpy(data, buf->base, (size_t)nread);
    if (buf->base) free(buf->base);
    uv_buf_t wbuf = uv_buf_init(data, (unsigned)nread);
    wreq->data = data;
    uv_write(wreq, stream, &wbuf, 1, on_server_write);
}

static void on_server_write(uv_write_t *req, int status) {
    (void)status;
    free(req->data);
    free(req);
}

static void on_client_read(uv_stream_t *stream, ssize_t nread, const uv_buf_t *buf) {
    (void)stream;
    if (nread == 4 && memcmp(buf->base, "ping", 4) == 0) echo_done = 1;
    if (buf->base) free(buf->base);
}

static void on_client_write(uv_write_t *req, int status) { (void)status; free(req); }

static void on_connect(uv_connect_t *req, int status) {
    CHECK(status == 0, "tcp connect");
    (void)req;
    if (status != 0) return;
    uv_buf_t buf = uv_buf_init("ping", 4);
    uv_write_t *wreq = malloc(sizeof(*wreq));
    uv_write(wreq, (uv_stream_t *)&client, &buf, 1, on_client_write);
    uv_read_start((uv_stream_t *)&client, alloc_cb, on_client_read);
}

static void on_connection(uv_stream_t *server_stream, int status) {
    CHECK(status == 0, "tcp accept");
    if (status != 0) return;
    uv_accept(server_stream, (uv_stream_t *)&peer);
    uv_read_start((uv_stream_t *)&peer, alloc_cb, on_server_read);
}

int main(int argc, char **argv) {
    if (argc < 2) { fprintf(stderr, "usage: %s FILE\n", argv[0]); return 2; }
    uv_loop_t loop_storage;
    loop = &loop_storage;
    int r = uv_loop_init(loop);
    CHECK(r == 0, "uv_loop_init");
    if (r != 0) return 1;

    uv_timer_t stop_timer;
    uv_timer_init(loop, &stop_timer);
    uv_timer_start(&stop_timer, on_stop_timer, 500, 0);

    r = uv_fs_open(loop, &open_req, argv[1], O_RDONLY, 0, on_open);
    CHECK(r == 0, "uv_fs_open");

    uv_timer_init(loop, &timer_req);
    uv_timer_start(&timer_req, on_timer, 10, 0);

    char *args[] = { "/bin/sh", "-c", "exit 23", NULL };
    child_opts.file = "/bin/sh";
    child_opts.args = args;
    child_opts.exit_cb = on_child_exit;
    r = uv_spawn(loop, &child_req, &child_opts);
    CHECK(r == 0, "uv_spawn");

    r = uv_queue_work(loop, &work_req, work_cb, after_work_cb);
    CHECK(r == 0, "uv_queue_work");

    uv_tcp_init(loop, &server);
    uv_tcp_init(loop, &client);
    uv_tcp_init(loop, &peer);
    struct sockaddr_in addr;
    uv_ip4_addr("127.0.0.1", 0, &addr);
    r = uv_tcp_bind(&server, (const struct sockaddr *)&addr, 0);
    CHECK(r == 0, "uv_tcp_bind");
    r = uv_listen((uv_stream_t *)&server, 1, on_connection);
    CHECK(r == 0, "uv_listen");
    int namelen = sizeof(addr);
    r = uv_tcp_getsockname(&server, (struct sockaddr *)&addr, &namelen);
    CHECK(r == 0, "uv_tcp_getsockname");
    uv_connect_t connect_req;
    r = uv_tcp_connect(&connect_req, &client, (const struct sockaddr *)&addr, on_connect);
    CHECK(r == 0, "uv_tcp_connect");

    uv_run(loop, UV_RUN_DEFAULT);

    CHECK(file_len > 0, "file read length");
    if (file_len > 0) CHECK(memcmp(file_buf, "alpha", 5) == 0, "file content");
    CHECK(child_exit_status == 23, "child exit code");
    CHECK(work_ran == 1, "work callback");
    CHECK(after_work_ran == 1, "after work callback");
    CHECK(timer_fired == 1, "timer callback");
    CHECK(echo_done == 1, "tcp echo");

    r = uv_loop_close(loop);
    CHECK(r == 0, "uv_loop_close (no leaked handles)");

    if (failures) {
        fprintf(stderr, "%d consumer checks failed\n", failures);
        return 1;
    }
    printf("consumer ok: fs read %zd bytes, child exit %d, work/timer/tcp echo verified, loop closed clean\n", file_len, child_exit_status);
    return 0;
}
