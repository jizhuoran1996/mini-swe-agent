/* Independent libevent CORE consumer (no TLS).
 *
 * Exercises the newly-built install from outside the source tree:
 * pthread locking via evthread_use_pthreads, a bufferevent_pair loopback
 * transfer, and a timer-bounded event_base_dispatch that exits in order.
 * Prints CONSUMER_OK only on success.
 */
#include <event2/event.h>
#include <event2/bufferevent.h>
#include <event2/buffer.h>
#include <event2/thread.h>

#include <stdio.h>
#include <string.h>

#define MSG "libevent-consumer-ping-payload"

static int matched = 0;

static void read_cb(struct bufferevent *bev, void *ctx)
{
    struct evbuffer *input = bufferevent_get_input(bev);
    char buf[512];
    int n;
    (void)ctx;
    n = evbuffer_remove(input, buf, (int)sizeof(buf) - 1);
    if (n > 0) {
        buf[n] = '\0';
        if (strcmp(buf, MSG) == 0)
            matched = 1;
    }
}

static void timeout_cb(evutil_socket_t fd, short what, void *ctx)
{
    struct event_base *base = (struct event_base *)ctx;
    (void)fd;
    (void)what;
    event_base_loopbreak(base);
}

int main(void)
{
    struct event_base *base;
    struct bufferevent *pair[2] = {NULL, NULL};
    struct event *timer;
    struct timeval tv;

    if (evthread_use_pthreads() != 0) {
        fprintf(stderr, "evthread_use_pthreads failed\n");
        return 2;
    }

    base = event_base_new();
    if (!base) {
        fprintf(stderr, "event_base_new failed\n");
        return 3;
    }

    if (bufferevent_pair_new(base, 0, pair) != 0) {
        fprintf(stderr, "bufferevent_pair_new failed\n");
        event_base_free(base);
        return 4;
    }

    bufferevent_setcb(pair[1], read_cb, NULL, NULL, NULL);
    if (bufferevent_enable(pair[1], EV_READ) != 0) {
        fprintf(stderr, "bufferevent_enable failed\n");
        return 5;
    }

    if (bufferevent_write(pair[0], MSG, strlen(MSG)) != 0) {
        fprintf(stderr, "bufferevent_write failed\n");
        return 6;
    }

    tv.tv_sec = 3;
    tv.tv_usec = 0;
    timer = event_new(base, -1, EV_TIMEOUT, timeout_cb, base);
    if (!timer || event_add(timer, &tv) != 0) {
        fprintf(stderr, "timer setup failed\n");
        return 7;
    }

    if (event_base_dispatch(base) < 0) {
        fprintf(stderr, "event_base_dispatch failed\n");
        return 8;
    }

    printf("backend=%s matched=%d\n", event_base_get_method(base), matched);

    event_free(timer);
    bufferevent_free(pair[0]);
    bufferevent_free(pair[1]);
    event_base_free(base);

    if (!matched) {
        printf("CONSUMER_FAIL\n");
        return 1;
    }
    printf("CONSUMER_OK\n");
    return 0;
}
