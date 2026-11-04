# Vulkan v5.0 Magma Core - API & RPC Reference Guide

## Document Information
- **Version**: 5.0
- **Server**: Actix-web / Tokio
- **Host**: 127.0.0.1:8000
- **CORS**: Enabled (all origins)
- **Total Endpoints**: 6 core RPC endpoints

## 1. Base URL
```
http://127.0.0.1:8000
```

## 2. Core RPC Endpoints

### 2.1 GET /chain/info

#### 2.1.1 Summary
Returns current chain state including block height, tip hash, and consensus parameters.

#### 2.1.2 Request
```
GET /chain/info
```
No parameters required.

#### 2.1.3 Response (200 OK)
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "jsonrpc": "2.0",
    "height": 2657847,
    "tip_hash": "0x3a2f...d4e1",
    "target": "0x0000AAAA...BBBB",
    "difficulty": "1.5x10^48",
    "timestamp": 1700006400,
    "supply_vul": "319850200.00",
    "supply_vulkano": "31985020000000000",
    "fee_burn_ppm": "450000",
    "era": 42,
    "async_mempool_count": 128
  }
}
```

#### 2.1.4 Field Descriptions
| Field | Type | Description |
|---|---|---|
| `height` | u64 | Current block height |
| `tip_hash` | hex string | Hash of current tip block |
| `target` | hex string | ASERT difficulty target |
| `difficulty` | string | Human-readable difficulty |
| `timestamp` | u64 | Current block timestamp |
| `supply_vul` | f64 | Total VUL supply (display) |
| `supply_vulkano` | u64 | Total supply in base units |
| `fee_burn_ppm` | u64 | Current fee burn rate (parts-per-million) |
| `era` | u64 | Current emission era |
| `async_mempool_count` | u64 | Pending transactions awaiting L1 settlement |

---

### 2.2 GET /mempool

#### 2.2.1 Summary
Returns pending transaction list and count from the mempool.

#### 2.2.2 Request
```
GET /mempool
```
No parameters required.

#### 2.2.3 Response (200 OK)
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "jsonrpc": "2.0",
    "tx_count": 42,
    "transactions": [
      {
        "tx_hash": "0xabc123...",
        "version": 1,
        "input_count": 1,
        "output_count": 2,
        "fee_vulkano": 5000,
        "status": "pending"
      }
    ]
  }
}
```

#### 2.2.4 Field Descriptions
| Field | Type | Description |
|---|---|---|
| `tx_count` | u64 | Total pending transactions |
| `transactions` | array | List of pending tx summaries |
| `tx_hash` | hex string | Transaction identifier |
| `version` | u32 | Transaction format version |
| `input_count` | u32 | Number of inputs |
| `output_count` | u32 | Number of outputs |
| `fee_vulkano` | u64 | Fee in base units |
| `status` | string | Transaction status (`pending`, `confirmed`) |

---

### 2.3 POST /miner/mine

#### 2.3.1 Summary
Mine N new blocks using single-threaded CPU PoW search.

#### 2.3.2 Request
```json
{
  "jsonrpc": "2.0",
  "method": "mine",
  "params": {
    "count": 1
  }
}
```

#### 2.3.3 Parameters
| Parameter | Type | Description | Default |
|---|---|---|---|
| `count` | u32 | Number of blocks to mine | 1 |

#### 2.3.4 Response (200 OK)
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "jsonrpc": "2.0",
    "mined_blocks": [
      {
        "block_hash": "0xabc123...",
        "block_height": 2657848,
        "timestamp": 1700006520,
        "target": "0x0000AAAA...BBBB",
        "tx_count": 1,
        "coinbase_tx_hash": "0x coinbase...",
        "status": "valid"
      }
    ],
    "total_mined": 1,
    "errors": []
  }
}
```

#### 2.3.5 Field Descriptions
| Field | Type | Description |
|---|---|---|
| `block_hash` | hex string | Hash of mined block |
| `block_height` | u64 | Height of new block |
| `timestamp` | u64 | Block creation timestamp |
| `target` | hex string | ASERT target used |
| `tx_count` | u32 | Number of transactions in block |
| `coinbase_tx_hash` | hex string | Coinbase transaction hash |
| `status` | string | Mine result (`valid`, `invalid`, `duplicate`) |
| `total_mined` | u32 | Total blocks attempted |
| `errors` | array | Any errors encountered |

---

### 2.4 POST /tx/send

#### 2.4.1 Summary
Submit a standard L1 P2PKH transaction to the mempool.

#### 2.4.2 Request
```json
{
  "jsonrpc": "2.0",
  "method": "tx_send",
  "params": {
    "version": 1,
    "inputs": [
      {
        "prev_tx_hash": "0xabc123...",
        "prev_index": 0,
        "script_sig": "",
        "sequence": 0xFFFFFFFF
      }
    ],
    "outputs": [
      {
        "value": 100000000,
        "script_pubkey": "<pubkey_hash>"
      }
    ],
    "lock_time": 0
  }
}
```

#### 2.4.3 Parameters
| Parameter | Type | Description |
|---|---|---|
| `version` | u32 | Transaction version |
| `inputs` | array | Transaction inputs |
| `prev_tx_hash` | hex string | Previous transaction hash |
| `prev_index` | u32 | Output index |
| `script_sig` | string | Unlocking script (signature) |
| `sequence` | u32 | Sequence number |
| `outputs` | array | Transaction outputs |
| `value` | u64 | Output value in vulkano |
| `script_pubkey` | string | Locking script (public key hash) |
| `lock_time` | u32 | Lock time field |

#### 2.4.4 Response (200 OK)
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "jsonrpc": "2.0",
    "status": "accepted",
    "tx_hash": "0xabc123...",
    "mempool_index": 42,
    "estimated_confirmations": 3
  }
}
```

#### 2.4.5 Response Fields
| Field | Type | Description |
|---|---|---|
| `status` | string | `accepted` / `rejected` / `duplicate` |
| `tx_hash` | hex string | Transaction hash (if accepted) |
| `mempool_index` | u64 | Position in mempool (if accepted) |
| `estimated_confirmations` | u64 | Expected blocks to confirmation |

---

### 2.5 POST /l2/earth/send

#### 2.5.1 Summary
Simulates L2 Earth Zero-Conf instant relay. Validates secp256k1 signature and memory non-double-spend, returns instant confirmation, queues tx for async L1 settlement.

#### 2.5.2 Request
```json
{
  "jsonrpc": "2.0",
  "method": "l2_earth_send",
  "params": {
    "tx_hash": "0xabc123...",
    "signature": "0x3045022100...",
    "public_key": "0x048b8a5...",
    "message_hash": "0xdeadbeef..."
  }
}
```

#### 2.5.3 Parameters
| Parameter | Type | Description |
|---|---|---|
| `tx_hash` | hex string | Transaction hash to confirm |
| `signature` | hex string | secp256k1 DER-encoded signature |
| `public_key` | hex string | secp256k1 compressed/public key |
| `message_hash` | hex string | Hash of the message/payload |

#### 2.5.4 Response (200 OK)
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "jsonrpc": "2.0",
    "instant_confirmation": true,
    "confirmed": true,
    "status": "instant",
    "settlement_queue": true,
    "settlement_txid": "0xsettlement...",
    "validation_details": {
      "signature_valid": true,
      "double_spend": false,
      "network_tag": "vulcan-main"
    }
  }
}
```

#### 2.5.5 Response Fields
| Field | Type | Description |
|---|---|---|
| `instant_confirmation` | bool | True if instant valid |
| `confirmed` | bool | Always true if instant_confirmation true |
| `status` | string | `instant` / `rejected` |
| `settlement_queue` | bool | Queued for L1 async settlement |
| `settlement_txid` | hex string | L1 transaction ID for settlement |
| `validation_details` | object | Per-validation results |
| `signature_valid` | bool | secp256k1 signature check |
| `double_spend` | bool | Non-double-spend memory check |
| `network_tag` | string | Network identifier (`vulcan-main`) |

---

### 2.6 POST /l2/magma/channel/open

#### 2.6.1 Summary
Opens a 2-of-2 HTLC state channel on L1 using OP_CHECKLOCKTIMEVERIFY script templates.

#### 2.6.2 Request
```json
{
  "jsonrpc": "2.0",
  "method": "l2_magma_channel_open",
  "params": {
    "participant_a": "<address_a>",
    "participant_b": "<address_b>",
    "funding_vulkano": 100000000,
    "timeout_blocks": 1000,
    "channel_name": "channel-test-001"
  }
}
```

#### 2.6.3 Parameters
| Parameter | Type | Description |
|---|---|---|
| `participant_a` | hex string | First participant address |
| `participant_b` | hex string | Second participant address |
| `funding_vulkano` | u64 | Channel funding amount in vulkano |
| `timeout_blocks` | u32 | HTLC timeout in blocks |
| `channel_name` | string | Human-readable channel identifier |

#### 2.6.4 Response (200 OK)
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "jsonrpc": "2.0",
    "status": "opened",
    "channel_id": "channel-test-001",
    "funding_tx_hash": "0xfunding...",
    "multisig_script": "<OP_CHECKSIG...>",
    "timeout_blocks": 1000,
    "funding_vulkano": 100000000,
    "participants": ["<addr_a>", "<addr_b>"]
  }
}
```

#### 2.6.5 Response Fields
| Field | Type | Description |
|---|---|---|
| `status` | string | `opened` / `failed` |
| `channel_id` | string | Unique channel identifier |
| `funding_tx_hash` | hex string | Funding transaction hash |
| `multisig_script` | string | 2-of-2 multisig script template |
| `timeout_blocks` | u32 | HTLC timeout duration |
| `funding_vulkano` | u64 | Channel funding in base units |
| `participants` | array | Two participant addresses |

---

## 3. Error Codes

| Code | Meaning | HTTP Status |
|---|---|---|
| `PARSE_ERROR` | Invalid JSON format | 400 |
| `INVALID_PARAMS` | Missing or invalid parameters | 400 |
| `TIMEOUT_ERROR` | Operation timed out | 408 |
| `NOT_FOUND` | Resource not found (block/tx) | 404 |
| `INSUFFICIENT_FUNDS` | Not enough VUL for transaction | 400 |
| `MEMPOOL_FULL` | Mempool at capacity | 429 |
| `VALIDATION_ERROR` | Transaction validation failed | 400 |
| `INTERNAL_ERROR` | Unexpected server error | 500 |

## 4. CORS Configuration

### 4.1 Allowed Origins
- `http://localhost:3000` (development dashboard)
- `http://127.0.0.1:8000` (self-referencing)
- `*` (for public API access, if enabled)

### 4.2 Allowed Methods
- `GET`, `POST`, `PUT`, `DELETE`
- `OPTIONS` (preflight)

### 4.3 Allowed Headers
- `Authorization`, `Content-Type`, `Accept`
- Custom headers as needed

### 4.4 Credentials
- Cookies and authentication headers allowed
- `withCredentials` supported for browser clients

## 5. Health Check

### 5.1 GET /health
```
GET /health
```
Response:
```json
{
  "status": "healthy",
  "server": "vulkan-rpc",
  "version": "5.0.0",
  "uptime": 3600
}
```

## 6. Version Compatibility

### 6.1 RPC Versioning
All responses include `jsonrpc: "2.0"` header.

### 6.2 Client Versioning
- Minimum client version: 5.0.0
- Deprecated endpoints marked with `deprecated: true`
- Breaking changes require new version release

## 7. API Usage Examples

### 6.1 Python Example
```python
import requests

# Get chain info
resp = requests.get('http://127.0.0.1:8000/chain/info')
data = resp.json()
print(f"Height: {data['result']['height']}")

# Send transaction
tx_data = {
    "version": 1,
    "inputs": [...],
    "outputs": [...],
    "lock_time": 0
}
resp = requests.post('http://127.0.0.1:8000/tx/send', json=tx_data)
print(f"Status: {resp.json()['result']['status']}")
```

### 6.2 Rust Example
```rust
use reqwest::Client;

let client = Client::new();
let info = client.get("http://127.0.0.1:8000/chain/info").send().await?.json().await?;
println!("Tip hash: {}", info.result.tip_hash);
```

---
*This document is part of the Vulkan v5.0 Magma Core technical wiki. 
All endpoints should be tested against the Rust RPC server and verified against the Python oracle.*