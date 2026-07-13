#define _GNU_SOURCE

#include <arpa/inet.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <poll.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <sys/types.h>
#include <time.h>
#include <unistd.h>

#ifndef AF_BLUETOOTH
#define AF_BLUETOOTH 31
#endif

#ifndef PF_BLUETOOTH
#define PF_BLUETOOTH AF_BLUETOOTH
#endif

#ifndef BTPROTO_L2CAP
#define BTPROTO_L2CAP 0
#endif

#ifndef SOL_BLUETOOTH
#define SOL_BLUETOOTH 274
#endif

#ifndef BT_SECURITY
#define BT_SECURITY 4
#endif

#define BT_SECURITY_LOW 1
#define BT_SECURITY_MEDIUM 2
#define BT_SECURITY_HIGH 3

#define BDADDR_BREDR 0x00
#define BDADDR_LE_PUBLIC 0x01
#define BDADDR_LE_RANDOM 0x02
#define ATT_CID 4

typedef struct {
    uint8_t b[6];
} __attribute__((packed)) bdaddr_t;

struct sockaddr_l2_local {
    sa_family_t l2_family;
    uint16_t l2_psm;
    bdaddr_t l2_bdaddr;
    uint16_t l2_cid;
    uint8_t l2_bdaddr_type;
};

struct bt_security_local {
    uint8_t level;
    uint8_t key_size;
};

static uint16_t le16(uint16_t v) {
#if __BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__
    return v;
#else
    return (uint16_t)((v >> 8) | (v << 8));
#endif
}

static int parse_bdaddr(const char *s, bdaddr_t *out) {
    unsigned int x[6];
    if (sscanf(s, "%02x:%02x:%02x:%02x:%02x:%02x",
               &x[0], &x[1], &x[2], &x[3], &x[4], &x[5]) != 6) {
        return -1;
    }
    for (int i = 0; i < 6; i++) {
        if (x[i] > 0xff) return -1;
        out->b[5 - i] = (uint8_t)x[i];
    }
    return 0;
}

static void die_errno(const char *what) {
    fprintf(stderr, "%s: %s\n", what, strerror(errno));
    exit(2);
}

static int send_all(int fd, const uint8_t *buf, size_t len) {
    ssize_t n = send(fd, buf, len, 0);
    if (n < 0) return -1;
    return (size_t)n == len ? 0 : -1;
}

static ssize_t recv_pkt(int fd, uint8_t *buf, size_t cap) {
    ssize_t n = recv(fd, buf, cap, 0);
    if (n < 0) return -1;
    printf("recv len=%zd", n);
    for (ssize_t i = 0; i < n && i < 48; i++) printf(" %02x", buf[i]);
    if (n > 48) printf(" ...");
    printf("\n");
    return n;
}

static int write_file(const char *path, const uint8_t *buf, size_t len) {
    FILE *f = fopen(path, "wb");
    if (!f) return -1;
    if (len && fwrite(buf, 1, len, f) != len) {
        fclose(f);
        return -1;
    }
    return fclose(f);
}

static int connect_wait(int fd, const struct sockaddr *addr, socklen_t addrlen,
                        int timeout_ms) {
    if (connect(fd, addr, addrlen) == 0) return 0;
    if (errno != EINPROGRESS && errno != EALREADY) return -1;

    struct pollfd pfd = {.fd = fd, .events = POLLOUT};
    int rc = poll(&pfd, 1, timeout_ms);
    if (rc <= 0) {
        errno = rc == 0 ? ETIMEDOUT : errno;
        return -1;
    }

    int err = 0;
    socklen_t err_len = sizeof(err);
    if (getsockopt(fd, SOL_SOCKET, SO_ERROR, &err, &err_len) < 0) return -1;
    if (err) {
        errno = err;
        return -1;
    }
    return 0;
}

static void wait_security_level(int fd, uint8_t wanted_level, int timeout_ms) {
    struct bt_security_local sec;
    socklen_t slen;
    int waited_ms = 0;

    while (waited_ms <= timeout_ms) {
        memset(&sec, 0, sizeof(sec));
        slen = sizeof(sec);
        if (getsockopt(fd, SOL_BLUETOOTH, BT_SECURITY, &sec, &slen) == 0) {
            printf("active security level=%u key_size=%u\n", sec.level, sec.key_size);
            if (sec.level >= wanted_level) return;
        }
        usleep(200000);
        waited_ms += 200;
    }
}

static int att_exchange_mtu(int fd, uint16_t mtu) {
    uint8_t req[3] = {0x02, (uint8_t)(mtu & 0xff), (uint8_t)(mtu >> 8)};
    uint8_t rsp[1024];
    printf("att exchange mtu request=%u\n", mtu);
    if (send_all(fd, req, sizeof(req)) < 0) return -1;
    ssize_t n = recv_pkt(fd, rsp, sizeof(rsp));
    if (n < 0) return -1;
    if (n >= 3 && rsp[0] == 0x03) {
        uint16_t peer = (uint16_t)rsp[1] | ((uint16_t)rsp[2] << 8);
        printf("att mtu peer=%u\n", peer);
        return peer;
    }
    if (n >= 5 && rsp[0] == 0x01) {
        printf("att mtu error req=0x%02x handle=0x%02x%02x code=0x%02x\n",
               rsp[1], rsp[3], rsp[2], rsp[4]);
    }
    return 23;
}

static ssize_t att_read_req(int fd, uint16_t handle, uint16_t offset,
                            uint8_t *out, size_t cap) {
    uint8_t req[5];
    size_t req_len;
    if (offset == 0) {
        req[0] = 0x0a;
        req[1] = (uint8_t)(handle & 0xff);
        req[2] = (uint8_t)(handle >> 8);
        req_len = 3;
        printf("att read handle=0x%04x\n", handle);
    } else {
        req[0] = 0x0c;
        req[1] = (uint8_t)(handle & 0xff);
        req[2] = (uint8_t)(handle >> 8);
        req[3] = (uint8_t)(offset & 0xff);
        req[4] = (uint8_t)(offset >> 8);
        req_len = 5;
        printf("att read-blob handle=0x%04x offset=%u\n", handle, offset);
    }
    if (send_all(fd, req, req_len) < 0) return -1;
    uint8_t rsp[4096];
    ssize_t n = recv_pkt(fd, rsp, sizeof(rsp));
    if (n < 0) return -1;
    if (n >= 5 && rsp[0] == 0x01) {
        printf("att error req=0x%02x handle=0x%04x code=0x%02x\n",
               rsp[1], (uint16_t)rsp[2] | ((uint16_t)rsp[3] << 8), rsp[4]);
        errno = EPROTO;
        return -1;
    }
    uint8_t expect = offset == 0 ? 0x0b : 0x0d;
    if (n < 1 || rsp[0] != expect) {
        fprintf(stderr, "unexpected att opcode 0x%02x, expected 0x%02x\n",
                n > 0 ? rsp[0] : 0, expect);
        errno = EPROTO;
        return -1;
    }
    size_t value_len = (size_t)n - 1;
    if (value_len > cap) value_len = cap;
    memcpy(out, rsp + 1, value_len);
    return (ssize_t)value_len;
}

static size_t read_long(int fd, uint16_t handle, uint8_t *buf, size_t cap,
                        size_t chunk_hint) {
    size_t total = 0;
    for (;;) {
        if (total >= cap || total > 65520) break;
        ssize_t n = att_read_req(fd, handle, (uint16_t)total, buf + total, cap - total);
        if (n < 0) {
            if (total > 0) break;
            return 0;
        }
        total += (size_t)n;
        printf("read handle=0x%04x total=%zu last=%zd\n", handle, total, n);
        if (n == 0) break;
        if (chunk_hint == 0 || (size_t)n < chunk_hint) break;
    }
    return total;
}

int main(int argc, char **argv) {
    if (argc < 3) {
        fprintf(stderr, "usage: %s <bdaddr> <outdir> [security:low|medium|high] [addr-type:public|random]\n", argv[0]);
        return 2;
    }
    const char *addr = argv[1];
    const char *outdir = argv[2];
    uint8_t sec_level = BT_SECURITY_HIGH;
    uint8_t addr_type = BDADDR_LE_PUBLIC;
    if (argc >= 4) {
        if (!strcmp(argv[3], "low")) sec_level = BT_SECURITY_LOW;
        else if (!strcmp(argv[3], "medium")) sec_level = BT_SECURITY_MEDIUM;
        else if (!strcmp(argv[3], "high")) sec_level = BT_SECURITY_HIGH;
        else {
            fprintf(stderr, "unknown security level: %s\n", argv[3]);
            return 2;
        }
    }
    if (argc >= 5) {
        if (!strcmp(argv[4], "public")) addr_type = BDADDR_LE_PUBLIC;
        else if (!strcmp(argv[4], "random")) addr_type = BDADDR_LE_RANDOM;
        else {
            fprintf(stderr, "unknown address type: %s\n", argv[4]);
            return 2;
        }
    }

    mkdir(outdir, 0755);

    bdaddr_t dst_addr;
    if (parse_bdaddr(addr, &dst_addr) < 0) {
        fprintf(stderr, "bad address: %s\n", addr);
        return 2;
    }

    int fd = socket(PF_BLUETOOTH, SOCK_SEQPACKET, BTPROTO_L2CAP);
    if (fd < 0) die_errno("socket");

    struct timeval tv = {.tv_sec = 12, .tv_usec = 0};
    setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
    setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof(tv));

    struct bt_security_local sec = {.level = sec_level, .key_size = 16};
    if (setsockopt(fd, SOL_BLUETOOTH, BT_SECURITY, &sec, sizeof(sec)) < 0) {
        die_errno("setsockopt BT_SECURITY");
    }
    printf("requested security level=%u key_size=%u\n", sec.level, sec.key_size);

    struct sockaddr_l2_local src;
    memset(&src, 0, sizeof(src));
    src.l2_family = AF_BLUETOOTH;
    src.l2_cid = le16(ATT_CID);
    src.l2_bdaddr_type = BDADDR_LE_PUBLIC;
    if (bind(fd, (struct sockaddr *)&src, sizeof(src)) < 0) die_errno("bind");

    struct sockaddr_l2_local dst;
    memset(&dst, 0, sizeof(dst));
    dst.l2_family = AF_BLUETOOTH;
    dst.l2_bdaddr = dst_addr;
    dst.l2_cid = le16(ATT_CID);
    dst.l2_bdaddr_type = addr_type;

    printf("connect le addr=%s type=%s att_cid=0x%04x\n",
           addr, addr_type == BDADDR_LE_PUBLIC ? "public" : "random", ATT_CID);
    if (connect_wait(fd, (struct sockaddr *)&dst, sizeof(dst), 30000) < 0) die_errno("connect");
    printf("connect ok\n");

    wait_security_level(fd, sec_level, 15000);

    int peer_mtu = att_exchange_mtu(fd, 517);
    size_t chunk_hint = peer_mtu > 1 ? (size_t)peer_mtu - 1 : 0;

    uint8_t uuid[512];
    ssize_t uuid_len = att_read_req(fd, 0x0077, 0, uuid, sizeof(uuid));
    if (uuid_len > 0) {
        char path[512];
        snprintf(path, sizeof(path), "%s/d401_uuid.bin", outdir);
        if (write_file(path, uuid, (size_t)uuid_len) < 0) die_errno("write d401");
        printf("saved d401 len=%zd\n", uuid_len);
    }

    uint8_t *report = calloc(1, 8 * 1024 * 1024);
    if (!report) die_errno("calloc");
    size_t report_len = read_long(fd, 0x0075, report, 8 * 1024 * 1024, chunk_hint);
    if (report_len > 0) {
        char path[512];
        snprintf(path, sizeof(path), "%s/d402_latest_report.bin", outdir);
        if (write_file(path, report, report_len) < 0) die_errno("write d402");
        printf("saved d402 len=%zu\n", report_len);
    }
    free(report);
    close(fd);
    return 0;
}
