// Minimal ATT client for the Dreem 2 headset.
// It avoids full GATT discovery so known-handle writes can run after MTU exchange.
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <getopt.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/select.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <unistd.h>

#include <bluetooth/bluetooth.h>
#include <bluetooth/hci.h>
#include <bluetooth/hci_lib.h>
#include <bluetooth/l2cap.h>

#define ATT_CID 4
#define ATT_DEFAULT_MTU 23
#define ATT_OP_ERROR_RSP 0x01
#define ATT_OP_MTU_REQ 0x02
#define ATT_OP_MTU_RSP 0x03
#define ATT_OP_READ_REQ 0x0a
#define ATT_OP_READ_RSP 0x0b
#define ATT_OP_WRITE_REQ 0x12
#define ATT_OP_WRITE_RSP 0x13
#define ATT_ECODE_REQ_NOT_SUPP 0x06

static uint16_t get_le16(const uint8_t *p)
{
	return p[0] | ((uint16_t)p[1] << 8);
}

static void put_le16(uint8_t *p, uint16_t v)
{
	p[0] = v & 0xff;
	p[1] = v >> 8;
}

static void print_hex(const uint8_t *data, size_t len)
{
	for (size_t i = 0; i < len; i++)
		printf("%02x", data[i]);
}

static int hexval(int c)
{
	if (c >= '0' && c <= '9')
		return c - '0';
	if (c >= 'a' && c <= 'f')
		return c - 'a' + 10;
	if (c >= 'A' && c <= 'F')
		return c - 'A' + 10;
	return -1;
}

static int read_hex_file(const char *path, uint8_t **out, size_t *out_len)
{
	FILE *fp = fopen(path, "r");
	char *buf = NULL;
	size_t cap = 0;
	size_t len = 0;
	int hi = -1;

	if (!fp) {
		perror(path);
		return -1;
	}

	while (1) {
		int c = fgetc(fp);
		int v;

		if (c == EOF)
			break;

		v = hexval(c);
		if (v < 0) {
			if (c == ' ' || c == '\n' || c == '\r' || c == '\t')
				continue;
			fprintf(stderr, "invalid hex character in %s\n", path);
			fclose(fp);
			free(buf);
			return -1;
		}

		if (hi < 0) {
			hi = v;
			continue;
		}

		if (len == cap) {
			size_t next = cap ? cap * 2 : 64;
			char *tmp = realloc(buf, next);
			if (!tmp) {
				fclose(fp);
				free(buf);
				return -1;
			}
			buf = tmp;
			cap = next;
		}

		buf[len++] = (hi << 4) | v;
		hi = -1;
	}

	fclose(fp);

	if (hi >= 0) {
		fprintf(stderr, "odd hex length in %s\n", path);
		free(buf);
		return -1;
	}

	*out = (uint8_t *)buf;
	*out_len = len;
	return 0;
}

static int connect_att(const char *adapter, const char *dst, uint8_t dst_type,
			int sec, int timeout_sec)
{
	bdaddr_t src_addr, dst_addr;
	int dev_id = -1;
	int sock;
	struct sockaddr_l2 srcaddr;
	struct sockaddr_l2 dstaddr;
	struct bt_security btsec;
	struct timeval tv;

	if (adapter) {
		dev_id = hci_devid(adapter);
		if (dev_id < 0) {
			perror("hci_devid");
			return -1;
		}
		if (hci_devba(dev_id, &src_addr) < 0) {
			perror("hci_devba");
			return -1;
		}
	} else {
		bacpy(&src_addr, BDADDR_ANY);
	}

	if (str2ba(dst, &dst_addr) < 0) {
		fprintf(stderr, "invalid destination address: %s\n", dst);
		return -1;
	}

	sock = socket(PF_BLUETOOTH, SOCK_SEQPACKET, BTPROTO_L2CAP);
	if (sock < 0) {
		perror("socket");
		return -1;
	}

	memset(&srcaddr, 0, sizeof(srcaddr));
	srcaddr.l2_family = AF_BLUETOOTH;
	srcaddr.l2_cid = htobs(ATT_CID);
	srcaddr.l2_bdaddr_type = 0;
	bacpy(&srcaddr.l2_bdaddr, &src_addr);

	if (bind(sock, (struct sockaddr *)&srcaddr, sizeof(srcaddr)) < 0) {
		perror("bind");
		close(sock);
		return -1;
	}

	memset(&btsec, 0, sizeof(btsec));
	btsec.level = sec;
	if (setsockopt(sock, SOL_BLUETOOTH, BT_SECURITY, &btsec,
			sizeof(btsec)) < 0) {
		perror("setsockopt BT_SECURITY");
		close(sock);
		return -1;
	}

	tv.tv_sec = timeout_sec;
	tv.tv_usec = 0;
	setsockopt(sock, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
	setsockopt(sock, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof(tv));

	memset(&dstaddr, 0, sizeof(dstaddr));
	dstaddr.l2_family = AF_BLUETOOTH;
	dstaddr.l2_cid = htobs(ATT_CID);
	dstaddr.l2_bdaddr_type = dst_type;
	bacpy(&dstaddr.l2_bdaddr, &dst_addr);

	printf("connect %s\n", dst);
	if (connect(sock, (struct sockaddr *)&dstaddr, sizeof(dstaddr)) < 0) {
		perror("connect");
		close(sock);
		return -1;
	}
	printf("connected\n");

	return sock;
}

static int send_error_rsp(int sock, uint8_t req_op, uint16_t handle,
			uint8_t ecode)
{
	uint8_t rsp[5];

	rsp[0] = ATT_OP_ERROR_RSP;
	rsp[1] = req_op;
	put_le16(&rsp[2], handle);
	rsp[4] = ecode;

	if (write(sock, rsp, sizeof(rsp)) != (ssize_t)sizeof(rsp)) {
		perror("write error response");
		return -1;
	}

	return 0;
}

static int handle_unsolicited(int sock, const uint8_t *pdu, ssize_t len,
			uint16_t local_mtu)
{
	uint8_t op;
	uint16_t handle = 0;

	if (len <= 0)
		return -1;

	op = pdu[0];

	if (op == ATT_OP_MTU_REQ && len >= 3) {
		uint8_t rsp[3];
		rsp[0] = ATT_OP_MTU_RSP;
		put_le16(&rsp[1], local_mtu);
		if (write(sock, rsp, sizeof(rsp)) != (ssize_t)sizeof(rsp)) {
			perror("write mtu response");
			return -1;
		}
		printf("peer_mtu_req %u\n", get_le16(&pdu[1]));
		return 0;
	}

	if (len >= 3)
		handle = get_le16(&pdu[1]);

	printf("peer_req_unsupported op=0x%02x\n", op);
	return send_error_rsp(sock, op, handle, ATT_ECODE_REQ_NOT_SUPP);
}

static int exchange_mtu(int sock, uint16_t mtu, int timeout_reads)
{
	uint8_t req[3];
	uint8_t pdu[1024];
	fd_set rfds;
	struct timeval tv;
	int ready;

	FD_ZERO(&rfds);
	FD_SET(sock, &rfds);
	tv.tv_sec = 2;
	tv.tv_usec = 0;
	ready = select(sock + 1, &rfds, NULL, NULL, &tv);
	if (ready < 0) {
		perror("select before mtu");
		return -1;
	}
	if (ready > 0) {
		ssize_t len = read(sock, pdu, sizeof(pdu));
		if (len < 0) {
			perror("read peer mtu request");
			return -1;
		}
		if (len > 0 && pdu[0] == ATT_OP_MTU_REQ && len >= 3) {
			uint16_t peer = get_le16(&pdu[1]);
			uint16_t negotiated = peer < mtu ? peer : mtu;
			if (handle_unsolicited(sock, pdu, len, mtu) < 0)
				return -1;
			if (negotiated < ATT_DEFAULT_MTU)
				negotiated = ATT_DEFAULT_MTU;
			printf("mtu %u\n", negotiated);
			return negotiated;
		}
		if (len > 0 && handle_unsolicited(sock, pdu, len, mtu) < 0)
			return -1;
	}

	req[0] = ATT_OP_MTU_REQ;
	put_le16(&req[1], mtu);

	if (write(sock, req, sizeof(req)) != (ssize_t)sizeof(req)) {
		perror("write mtu request");
		return -1;
	}

	for (int i = 0; i < timeout_reads; i++) {
		ssize_t len = read(sock, pdu, sizeof(pdu));

		if (len < 0) {
			perror("read mtu response");
			return -1;
		}
		if (len == 0)
			continue;

		if (pdu[0] == ATT_OP_MTU_RSP && len >= 3) {
			uint16_t peer = get_le16(&pdu[1]);
			uint16_t negotiated = peer < mtu ? peer : mtu;
			if (negotiated < ATT_DEFAULT_MTU)
				negotiated = ATT_DEFAULT_MTU;
			printf("mtu %u\n", negotiated);
			return negotiated;
		}

		if (pdu[0] == ATT_OP_ERROR_RSP && len >= 5 && pdu[1] == ATT_OP_MTU_REQ) {
			fprintf(stderr, "mtu_error ecode=0x%02x\n", pdu[4]);
			return ATT_DEFAULT_MTU;
		}

		if (handle_unsolicited(sock, pdu, len, mtu) < 0)
			return -1;
	}

	fprintf(stderr, "mtu exchange timed out\n");
	return -1;
}

static int wait_for_response(int sock, uint8_t expected_op, uint8_t req_op,
			uint16_t handle, uint16_t mtu, uint8_t **out,
			size_t *out_len)
{
	uint8_t pdu[4096];

	while (1) {
		ssize_t len = read(sock, pdu, sizeof(pdu));

		if (len < 0) {
			perror("read response");
			return -1;
		}
		if (len == 0)
			continue;

		if (pdu[0] == expected_op) {
			if (out) {
				*out_len = (size_t)len - 1;
				*out = malloc(*out_len);
				if (!*out)
					return -1;
				memcpy(*out, pdu + 1, *out_len);
			}
			return 0;
		}

		if (pdu[0] == ATT_OP_ERROR_RSP && len >= 5 && pdu[1] == req_op) {
			fprintf(stderr, "att_error handle=0x%04x req=0x%02x ecode=0x%02x\n",
				get_le16(&pdu[2]), req_op, pdu[4]);
			return -(int)pdu[4];
		}

		if (handle_unsolicited(sock, pdu, len, mtu) < 0)
			return -1;
	}
}

static int att_read(int sock, uint16_t handle, uint16_t mtu)
{
	uint8_t req[3];
	uint8_t *value = NULL;
	size_t value_len = 0;
	int rc;

	req[0] = ATT_OP_READ_REQ;
	put_le16(&req[1], handle);

	if (write(sock, req, sizeof(req)) != (ssize_t)sizeof(req)) {
		perror("write read request");
		return -1;
	}

	rc = wait_for_response(sock, ATT_OP_READ_RSP, ATT_OP_READ_REQ, handle,
				mtu, &value, &value_len);
	if (rc < 0)
		return rc;

	printf("read handle=0x%04x len=%zu hex=", handle, value_len);
	print_hex(value, value_len);
	printf("\n");
	free(value);
	return 0;
}

static int att_write(int sock, uint16_t handle, const uint8_t *value,
			size_t value_len, uint16_t mtu)
{
	uint8_t *req;
	int rc;

	if (value_len > (size_t)mtu - 3) {
		fprintf(stderr, "value length %zu exceeds mtu payload %u\n",
			value_len, mtu - 3);
		return -1;
	}

	req = malloc(value_len + 3);
	if (!req)
		return -1;

	req[0] = ATT_OP_WRITE_REQ;
	put_le16(&req[1], handle);
	memcpy(req + 3, value, value_len);

	if (write(sock, req, value_len + 3) != (ssize_t)(value_len + 3)) {
		perror("write write-request");
		free(req);
		return -1;
	}
	free(req);

	rc = wait_for_response(sock, ATT_OP_WRITE_RSP, ATT_OP_WRITE_REQ, handle,
				mtu, NULL, NULL);
	if (rc < 0)
		return rc;

	printf("write handle=0x%04x len=%zu ok\n", handle, value_len);
	return 0;
}

static void usage(const char *prog)
{
	fprintf(stderr,
		"Usage: %s -d MAC [-i hci0] [-m mtu] [-M] [-t public|random] [-s low|medium|high] op...\n"
		"Ops:\n"
		"  read HANDLE\n"
		"  write HANDLE HEXFILE\n"
		"Options:\n"
		"  -M  skip MTU exchange and use the default ATT MTU\n", prog);
}

int main(int argc, char **argv)
{
	const char *adapter = "hci0";
	const char *dst = NULL;
	uint8_t dst_type = BDADDR_LE_PUBLIC;
	int sec = BT_SECURITY_LOW;
	uint16_t requested_mtu = 200;
	uint16_t mtu;
	int negotiated_mtu;
	int sock;
	int opt;
	bool skip_mtu = false;

	while ((opt = getopt(argc, argv, "i:d:t:m:s:Mh")) != -1) {
		switch (opt) {
		case 'i':
			adapter = optarg;
			break;
		case 'd':
			dst = optarg;
			break;
		case 't':
			if (!strcmp(optarg, "public"))
				dst_type = BDADDR_LE_PUBLIC;
			else if (!strcmp(optarg, "random"))
				dst_type = BDADDR_LE_RANDOM;
			else {
				usage(argv[0]);
				return 2;
			}
			break;
		case 'm':
			requested_mtu = (uint16_t)atoi(optarg);
			break;
		case 's':
			if (!strcmp(optarg, "low"))
				sec = BT_SECURITY_LOW;
			else if (!strcmp(optarg, "medium"))
				sec = BT_SECURITY_MEDIUM;
			else if (!strcmp(optarg, "high"))
				sec = BT_SECURITY_HIGH;
			else {
				usage(argv[0]);
				return 2;
			}
			break;
		case 'M':
			skip_mtu = true;
			break;
		default:
			usage(argv[0]);
			return 2;
		}
	}

	if (!dst || optind >= argc) {
		usage(argv[0]);
		return 2;
	}

	sock = connect_att(adapter, dst, dst_type, sec, 45);
	if (sock < 0)
		return 1;

	if (skip_mtu) {
		negotiated_mtu = ATT_DEFAULT_MTU;
		printf("mtu %u skipped\n", negotiated_mtu);
	} else {
		negotiated_mtu = exchange_mtu(sock, requested_mtu, 8);
		if (negotiated_mtu < 0) {
			close(sock);
			return 1;
		}
	}
	mtu = (uint16_t)negotiated_mtu;

	while (optind < argc) {
		const char *op = argv[optind++];
		uint16_t handle;
		char *endptr = NULL;

		if (optind >= argc) {
			usage(argv[0]);
			close(sock);
			return 2;
		}

		handle = (uint16_t)strtol(argv[optind++], &endptr, 0);
		if (!endptr || *endptr != '\0' || handle == 0) {
			fprintf(stderr, "invalid handle\n");
			close(sock);
			return 2;
		}

		if (!strcmp(op, "read")) {
			if (att_read(sock, handle, mtu) < 0) {
				close(sock);
				return 1;
			}
		} else if (!strcmp(op, "write")) {
			uint8_t *value = NULL;
			size_t value_len = 0;

			if (optind >= argc) {
				usage(argv[0]);
				close(sock);
				return 2;
			}

			if (read_hex_file(argv[optind++], &value, &value_len) < 0) {
				close(sock);
				return 1;
			}

			if (att_write(sock, handle, value, value_len, mtu) < 0) {
				free(value);
				close(sock);
				return 1;
			}
			free(value);
		} else {
			usage(argv[0]);
			close(sock);
			return 2;
		}
	}

	close(sock);
	return 0;
}
