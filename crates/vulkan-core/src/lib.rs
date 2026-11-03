use pyo3::prelude::*;
use pyo3::types::PyBytes;
use sha2::{Sha256, Digest};

const MAX_MONEY: u64 = 32_000_000_000 * 100_000_000;

// Double SHA-256 hash
fn double_sha256(data: &[u8]) -> Vec<u8> {
    let mut h1 = Sha256::new();
    h1.update(data);
    let first = h1.finalize().to_vec();
    let mut h2 = Sha256::new();
    h2.update(&first);
    h2.finalize().to_vec()
}

// Varint encoding
fn encode_varint(value: u64) -> Vec<u8> {
    if value < 0xFD {
        return vec![value as u8];
    }
    if value <= 0xFFFF {
        let mut v = vec![0xfd];
        v.extend_from_slice(&value.to_le_bytes()[..2]);
        v
    } else if value <= 0xFFFFFFFF {
        let mut v = vec![0xfe];
        v.extend_from_slice(&value.to_le_bytes()[..4]);
        v
    } else {
        let mut v = vec![0xff];
        v.extend_from_slice(&value.to_le_bytes());
        v
    }
}

/// Read unsigned LEB128 varint from bytes at offset, returns (value, new_offset)
fn read_varint(data: &[u8], offset: usize) -> Result<(u64, usize), String> {
    if offset >= data.len() { return Err("offset out of bounds".to_string()); }
    let b = data[offset];
    if b < 0xFD {
        Ok((b as u64, offset + 1))
    } else if b == 0xFD {
        if offset + 3 > data.len() { return Err("data too short".to_string()); }
        let val = u16::from_le_bytes(data[offset+1..offset+3].try_into().map_err(|_| "")?);
        Ok((val as u64, offset + 3))
    } else if b == 0xFE {
        if offset + 5 > data.len() { return Err("data too short".to_string()); }
        let val = u32::from_le_bytes(data[offset+1..offset+5].try_into().map_err(|_| "")?);
        Ok((val as u64, offset + 5))
    } else {
        if offset + 9 > data.len() { return Err("data too short".to_string()); }
        let val = u64::from_le_bytes(data[offset+1..offset+9].try_into().map_err(|_| "")?);
        Ok((val, offset + 9))
    }
}

// === TxIn ===

#[pyclass(name = "TxIn", frozen, subclass)]
#[derive(Clone)]
pub struct PyTxIn {
    pub prev_txid: Vec<u8>,
    pub prev_index: u32,
    pub script_sig: Vec<u8>,
    pub sequence: u32,
}

#[pymethods]
impl PyTxIn {
    #[new]
    fn new(prev_txid: Vec<u8>, prev_index: u64, script_sig: Vec<u8>, sequence: u64) -> PyResult<Self> {
        if prev_txid.len() != 32 {
            return Err(pyo3::exceptions::PyValueError::new_err("prev_txid must be 32 bytes"));
        }
        if prev_index > 0xFFFFFFFF {
            return Err(pyo3::exceptions::PyValueError::new_err("prev_index out of range"));
        }
        if sequence > 0xFFFFFFFF {
            return Err(pyo3::exceptions::PyValueError::new_err("sequence out of range"));
        }
        Ok(PyTxIn {
            prev_txid,
            prev_index: prev_index as u32,
            script_sig,
            sequence: sequence as u32,
        })
    }

    #[getter]
    fn prev_txid(&self) -> Vec<u8> { self.prev_txid.clone() }
    #[getter]
    fn prev_index(&self) -> u64 { self.prev_index as u64 }
    #[getter]
    fn script_sig(&self) -> Vec<u8> { self.script_sig.clone() }
    #[getter]
    fn sequence(&self) -> u64 { self.sequence as u64 }

    fn is_null(&self) -> bool {
        self.prev_txid == vec![0u8; 32] && self.prev_index == 0xFFFFFFFF
    }

    fn serialize(&self) -> Vec<u8> {
        let mut r = vec![];
        r.extend_from_slice(&self.prev_txid);
        r.extend_from_slice(&self.prev_index.to_le_bytes());
        r.extend_from_slice(&encode_varint(self.script_sig.len() as u64));
        r.extend_from_slice(&self.script_sig);
        r.extend_from_slice(&self.sequence.to_le_bytes());
        r
    }

    #[staticmethod]
    fn from_bytes(data: &PyBytes) -> PyResult<Self> {
        let d = data.as_bytes();
        if d.len() < 67 { return Err(pyo3::exceptions::PyValueError::new_err("invalid txin data")); }
        let (sig_len, off) = read_varint(d, 35).map_err(|e| pyo3::exceptions::PyValueError::new_err(e))?;
        if off as usize + sig_len as usize + 4 > d.len() { 
            return Err(pyo3::exceptions::PyValueError::new_err("invalid txin data")); 
        }
        let sig = d[off..off+sig_len as usize].to_vec();
        Ok(PyTxIn {
            prev_txid: d[0..32].to_vec(),
            prev_index: u32::from_le_bytes(d[32..36].try_into().unwrap()),
            script_sig: sig,
            sequence: u32::from_le_bytes(d[d.len()-4..].try_into().unwrap()),
        })
    }

    fn __str__(&self) -> String {
        let hex: String = self.prev_txid.iter().map(|b| format!("{:02x}", b)).collect();
        format!("TxIn({}, {})", hex, self.prev_index)
    }
}

// === TxOut ===

#[pyclass(name = "TxOut", frozen, subclass)]
#[derive(Clone)]
pub struct PyTxOut {
    pub value: u64,
    pub script_pubkey: Vec<u8>,
}

#[pymethods]
impl PyTxOut {
    #[new]
    fn new(value: u64, script_pubkey: Vec<u8>) -> PyResult<Self> {
        if value > MAX_MONEY {
            return Err(pyo3::exceptions::PyValueError::new_err(format!("value {} exceeds MAX_MONEY {}", value, MAX_MONEY)));
        }
        Ok(PyTxOut { value, script_pubkey })
    }

    #[getter]
    fn value(&self) -> u64 { self.value }
    #[getter]
    fn script_pubkey(&self) -> Vec<u8> { self.script_pubkey.clone() }

    fn serialize(&self) -> Vec<u8> {
        let mut r = vec![];
        r.extend_from_slice(&self.value.to_le_bytes());
        r.extend_from_slice(&encode_varint(self.script_pubkey.len() as u64));
        r.extend_from_slice(&self.script_pubkey);
        r
    }

    #[staticmethod]
    fn from_reader(data: &PyBytes) -> PyResult<Self> {
        let d = data.as_bytes();
        if d.len() < 8 { return Err(pyo3::exceptions::PyValueError::new_err("invalid txout data")); }
        let script_len = d[8] as usize;
        if 9 + script_len > d.len() { return Err(pyo3::exceptions::PyValueError::new_err("invalid txout data")); }
        let script = d[9..9+script_len].to_vec();
        let value = u64::from_le_bytes(d[0..8].try_into().unwrap());
        Ok(PyTxOut { value, script_pubkey: script })
    }

    fn __str__(&self) -> String {
        format!("TxOut(value={}, script_pubkey_len={})", self.value, self.script_pubkey.len())
    }
}

// === Transaction ===

#[pyclass(name = "Transaction", frozen, subclass)]
#[derive(Clone)]
pub struct PyTx {
    pub version: u32,
    pub inputs: Vec<PyTxIn>,
    pub outputs: Vec<PyTxOut>,
    pub lock_time: u32,
}

#[pymethods]
impl PyTx {
    #[new]
    fn new(version: u64, inputs: Vec<PyTxIn>, outputs: Vec<PyTxOut>, lock_time: u64) -> PyResult<Self> {
        if version > 0xFFFFFFFF {
            return Err(pyo3::exceptions::PyValueError::new_err("version out of range"));
        }
        if lock_time > 0xFFFFFFFF {
            return Err(pyo3::exceptions::PyValueError::new_err("lock_time out of range"));
        }
        Ok(PyTx {
            version: version as u32,
            inputs,
            outputs,
            lock_time: lock_time as u32,
        })
    }

    #[getter]
    fn version(&self) -> u64 { self.version as u64 }
    #[getter]
    fn inputs(&self) -> Vec<PyTxIn> { self.inputs.clone() }
    #[getter]
    fn outputs(&self) -> Vec<PyTxOut> { self.outputs.clone() }
    #[getter]
    fn lock_time(&self) -> u64 { self.lock_time as u64 }

    fn is_coinbase(&self) -> bool {
        self.inputs.len() == 1 && self.inputs[0].is_null()
    }

    fn txid(&self) -> PyObject {
        let data = self.serialize();
        let hash = double_sha256(&data);
        let hex_str: String = hash.iter().map(|b| format!("{:02x}", b)).collect();
        // Use unsafe assume_gil_acquired to get Python token
        let py = unsafe { pyo3::Python::assume_gil_acquired() };
        pyo3::types::PyString::new(py, &hex_str).into()
    }

    fn serialize(&self) -> Vec<u8> {
        let mut parts = vec![];
        parts.extend_from_slice(&encode_varint(self.version as u64));
        parts.extend_from_slice(&encode_varint(self.inputs.len() as u64));
        for txin in &self.inputs { parts.extend_from_slice(&txin.serialize()); }
        parts.extend_from_slice(&encode_varint(self.outputs.len() as u64));
        for txout in &self.outputs { parts.extend_from_slice(&txout.serialize()); }
        parts.extend_from_slice(&self.lock_time.to_le_bytes());
        parts
    }

    #[staticmethod]
    fn from_bytes(data: &PyBytes) -> PyResult<Self> {
        let d = data.as_bytes();
        if d.len() < 4 { return Err(pyo3::exceptions::PyValueError::new_err("transaction data too short")); }
        Err(pyo3::exceptions::PyValueError::new_err("full from_bytes needs ByteReader implementation"))
    }

    fn validate(&self) -> PyResult<()> {
        if self.inputs.is_empty() { return Err(pyo3::exceptions::PyValueError::new_err("transaction has no inputs")); }
        if self.outputs.is_empty() { return Err(pyo3::exceptions::PyValueError::new_err("transaction has no outputs")); }
        for txin in &self.inputs {
            if !txin.is_null() && txin.prev_txid == vec![0u8; 32] {
                return Err(pyo3::exceptions::PyValueError::new_err("null prevout only allowed in coinbase"));
            }
        }
        Ok(())
    }

    fn __str__(&self) -> String {
        format!("Tx({}, inputs={}, outputs={})", self.version, self.inputs.len(), self.outputs.len())
    }
}

// === Module initializer ===

#[pymodule]
fn vulkan_core(_py: pyo3::Python, m: &pyo3::types::PyModule) -> PyResult<()> {
    m.add_wrapped(wrap_pyfunction!(double_sha256_py))?;
    m.add_wrapped(wrap_pyfunction!(encode_varint_py))?;
    m.add_wrapped(wrap_pyfunction!(transaction_from_bytes))?;
    m.add_class::<PyTxIn>()?;
    m.add_class::<PyTxOut>()?;
    m.add_class::<PyTx>()?;
    Ok(())
}

// === Module-level functions ===

#[pyfunction]
fn double_sha256_py(data: &PyBytes) -> PyResult<String> {
    let d = data.as_bytes();
    let hash = double_sha256(d);
    let hex_str: String = hash.iter().map(|b| format!("{:02x}", b)).collect();
    Ok(hex_str)
}

#[pyfunction]
fn encode_varint_py(value: u64) -> Vec<u8> {
    encode_varint(value)
}

#[pyfunction]
fn transaction_from_bytes(data: &PyBytes) -> PyResult<PyTx> {
    let d = data.as_bytes();
    if d.len() < 4 {
        return Err(pyo3::exceptions::PyValueError::new_err("transaction data too short"));
    }
    Err(pyo3::exceptions::PyValueError::new_err("full from_bytes needs ByteReader implementation"))
}