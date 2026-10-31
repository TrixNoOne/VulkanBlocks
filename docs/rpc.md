# Vulkan JSON-RPC HTTP Contract

This document is the stable JSON-RPC 2.0 over HTTP contract for a Vulkan node.
It is intended to be given to client and integration developers. Field names
and error codes are frozen once published; changes require a new version of
this document.

## Transport

- **Method:** `POST`
- **Content-Type:** `application/json`
- **Body:** a single JSON-RPC 2.0 request object
- **Response:** `application/json`, a single JSON-RPC 2.0 response object
- HTTP status is `200 OK` for a well-formed JSON-RPC response (even when the
  application returns an error); `400` for malformed bodies, `429` when
  rate-limited.

## JSON-RPC envelope

Every request:

```json
{
  "jsonrpc": "2.0",
  "method": "gettip",
  "params": { ... },
  "id": 1
}
```

Every success response:

```json
{
  "jsonrpc": "2.0",
  "result": { ... },
  "id": 1
}
```

Every error response:

```json
{
  "jsonrpc": "2.0",
  "error": {
    "code": -32600,
    "message": "Invalid request",
    "data": null
  },
  "id": 1
}
```

`params` is always an object (named parameters), never a positional array.

## Units and encodings

- **Monetary amounts:** integers in units of 10^-8 VUL (one "unit"). No floats
  anywhere. `1 VUL = 100_000_000` units.
- **Hashes:** lowercase hex strings, no `0x` prefix. Block hashes are 64 bytes
  (128 hex chars, double SHA-512); transaction ids are 32 bytes (64 hex chars,
  double SHA-256).
- **Public keys / scripts / signatures / raw transactions:** lowercase hex
  strings.
- **Timestamps / heights / amounts / nonces:** unsigned integers.
- **Booleans:** JSON `true` / `false`.

## Standard error codes

| Code | Meaning |
|------|---------|
| -32700 | Parse error (invalid JSON) |
| -32600 | Invalid request |
| -32601 | Method not found |
| -32602 | Invalid params |
| -32603 | Internal error |
| -32001 | Resource not found (block/tx/address not known) |
| -32002 | Invalid transaction (rejected by validation) |
| -32003 | Chain error (orphan, reorg conflict, checkpoint) |
| -32004 | Rate limited |
| -32005 | Node not synced / no tip available |

Application errors carry `code <= -32000` and may include a `data` field with
additional context.

---

## Methods

### getblocktemplate

Ask the node for a block template ready to mine. Returns the current height,
target, previous hash, a coinbase transaction paying the requester, and the
list of pending transactions to include.

**Request**

```json
{ "method": "getblocktemplate", "params": {}, "id": 1 }
```

No parameters.

**Response**

| Field | Type | Description |
|-------|------|-------------|
| `height` | uint32 | Height of the block to mine |
| `previous_hash` | hex (64 bytes) | Hash of the tip block |
| `timestamp` | uint64 | Suggested block timestamp (seconds since epoch) |
| `target` | hex (64 bytes, big-endian) | PoW target for this height |
| `coinbase` | hex | Serialized coinbase transaction (pays to requester) |
| `transactions` | array of hex | Serialized non-coinbase transactions to include |
| `fees` | array of uint64 | Fee of each transaction, same order as `transactions` |
| `max_block_size` | uint64 | 1_000_000 |

**Example**

```json
{
  "jsonrpc": "2.0",
  "result": {
    "height": 42,
    "previous_hash": "0000...abcd",
    "timestamp": 1793318520,
    "target": "0000...ffff",
    "coinbase": "010000...",
    "transactions": ["010000...", "010001..."],
    "fees": [10000, 5000],
    "max_block_size": 1000000
  },
  "id": 1
}
```

**Errors:** `-32005` if the node has no tip yet.

---

### submitblock

Submit a fully solved block header and transaction list for acceptance.

**Request**

| Field | Type | Description |
|-------|------|-------------|
| `block` | hex | Serialized block (header + transactions) |

```json
{ "method": "submitblock", "params": { "block": "010000..." }, "id": 2 }
```

**Response**

| Field | Type | Description |
|-------|------|-------------|
| `accepted` | boolean | `true` if the block became part of the active chain |
| `status` | string | `"accepted"`, `"orphan"`, `"duplicate"`, or `"invalid"` |
| `reason` | string | Human-readable reason (empty when accepted) |
| `tip` | hex (64 bytes) | Active tip hash after processing |

**Example**

```json
{
  "jsonrpc": "2.0",
  "result": { "accepted": true, "status": "accepted", "reason": "", "tip": "..." },
  "id": 2
}
```

**Errors:** `-32002` for an invalid block, `-32003` for chain conflicts.

---

### sendtx

Broadcast a signed transaction to the mempool.

**Request**

| Field | Type | Description |
|-------|------|-------------|
| `tx` | hex | Serialized, fully signed transaction |

```json
{ "method": "sendtx", "params": { "tx": "010000..." }, "id": 3 }
```

**Response**

| Field | Type | Description |
|-------|------|-------------|
| `txid` | hex (32 bytes) | Transaction id |
| `accepted` | boolean | `true` if accepted into the mempool |
| `reason` | string | Human-readable reason (empty when accepted) |

**Errors:** `-32002` if the transaction is invalid or a double-spend.

---

### getbalance

Return the confirmed balance of an address.

**Request**

| Field | Type | Description |
|-------|------|-------------|
| `address` | string | Base58Check Vulcan address |

```json
{ "method": "getbalance", "params": { "address": "boAJHP..." }, "id": 4 }
```

**Response**

| Field | Type | Description |
|-------|------|-------------|
| `address` | string | The queried address |
| `balance` | uint64 | Balance in units of 10^-8 VUL |

**Errors:** `-32001` if the address format is invalid.

---

### getutxos

List the unspent transaction outputs controlled by an address.

**Request**

| Field | Type | Description |
|-------|------|-------------|
| `address` | string | Base58Check Vulcan address |

```json
{ "method": "getutxos", "params": { "address": "boAJHP..." }, "id": 5 }
```

**Response**

| Field | Type | Description |
|-------|------|-------------|
| `address` | string | The queried address |
| `utxos` | array | List of unspent outputs |

Each utxo object:

| Field | Type | Description |
|-------|------|-------------|
| `txid` | hex (32 bytes) | Funding transaction id |
| `vout` | uint32 | Output index |
| `value` | uint64 | Amount in units of 10^-8 VUL |
| `script_pubkey` | hex | P2PKH script |
| `height` | uint32 | Block height that created the output |
| `coinbase` | boolean | `true` if the output is a coinbase output |

**Errors:** `-32001` if the address format is invalid.

---

### getblock

Fetch a block by hash or by height. Exactly one of `hash` or `height` must be
provided.

**Request**

| Field | Type | Description |
|-------|------|-------------|
| `hash` | hex (64 bytes) | Block hash (optional) |
| `height` | uint32 | Block height (optional) |

```json
{ "method": "getblock", "params": { "height": 42 }, "id": 6 }
```

or

```json
{ "method": "getblock", "params": { "hash": "0000...abcd" }, "id": 6 }
```

**Response**

| Field | Type | Description |
|-------|------|-------------|
| `hash` | hex (64 bytes) | Block hash |
| `height` | uint32 | Block height |
| `previous_hash` | hex (64 bytes) | Parent block hash |
| `merkle_root` | hex (32 bytes) | Merkle root of transactions |
| `timestamp` | uint64 | Block timestamp |
| `target` | hex (64 bytes) | PoW target |
| `nonce` | uint64 | Proof-of-work nonce |
| `work` | string | Cumulative work as decimal string |
| `status` | string | `"active"`, `"valid"`, or `"invalid"` |
| `transactions` | array of hex | Serialized transactions |

**Errors:** `-32001` if the block is unknown.

---

### gettx

Fetch a transaction by id.

**Request**

| Field | Type | Description |
|-------|------|-------------|
| `txid` | hex (32 bytes) | Transaction id |

```json
{ "method": "gettx", "params": { "txid": "abcd..." }, "id": 7 }
```

**Response**

| Field | Type | Description |
|-------|------|-------------|
| `txid` | hex (32 bytes) | Transaction id |
| `serialized` | hex | Serialized transaction |
| `version` | uint32 | Transaction version |
| `lock_time` | uint32 | Lock time (block height) |
| `inputs` | array | Transaction inputs |
| `outputs` | array | Transaction outputs |
| `fee` | uint64 | Fee in units of 10^-8 VUL (null for coinbase) |
| `block_hash` | hex (64 bytes) | Block containing the tx, or null if unconfirmed |
| `block_height` | uint32 | Height of the block, or null if unconfirmed |

Each input:

| Field | Type | Description |
|-------|------|-------------|
| `prev_txid` | hex (32 bytes) | Funding transaction id |
| `vout` | uint32 | Funding output index |
| `script_sig` | hex | Unlocking script |
| `sequence` | uint32 | Sequence number |

Each output:

| Field | Type | Description |
|-------|------|-------------|
| `value` | uint64 | Amount in units of 10^-8 VUL |
| `script_pubkey` | hex | Locking script |

**Errors:** `-32001` if the transaction is unknown.

---

### gettip

Return the current chain tip.

**Request**

```json
{ "method": "gettip", "params": {}, "id": 8 }
```

No parameters.

**Response**

| Field | Type | Description |
|-------|------|-------------|
| `hash` | hex (64 bytes) | Tip block hash |
| `height` | uint32 | Tip height |
| `timestamp` | uint64 | Tip timestamp |
| `work` | string | Cumulative work as decimal string |

**Errors:** `-32005` if the node has no tip yet.

---

### getpeers

List connected peers.

**Request**

```json
{ "method": "getpeers", "params": {}, "id": 9 }
```

No parameters.

**Response**

| Field | Type | Description |
|-------|------|-------------|
| `peers` | array of strings | Peer addresses (`host:port`) |

---

### getmempool

List transactions in the mempool.

**Request**

```json
{ "method": "getmempool", "params": {}, "id": 10 }
```

No parameters.

**Response**

| Field | Type | Description |
|-------|------|-------------|
| `count` | uint32 | Number of transactions |
| `txids` | array of hex (32 bytes) | Transaction ids |
| `total_fees` | uint64 | Sum of fees in units of 10^-8 VUL |

---

## Versioning

This is contract version `1.0`. Backward-incompatible changes will be
published as a new version of this document and signaled by the node's
implementation, never by silently changing field names or error codes.
