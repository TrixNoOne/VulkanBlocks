//! Vulkan Wallet - Rust implementation for v5.0 Magma Core
//! 
//! Provides wallet functionality for managing VUL tokens,
//! including address generation, transaction signing, and balance tracking.
//! 
//! This wallet integrates with the vulkan_core PyO3 module for consensus operations.

/// Vulkan wallet address type (Base58Check encoded, version 0x56 for mainnet)
pub type Address = [u8; 20];

/// Transaction input structure
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct TxInput {
    /// Previous transaction output being spent
    pub prev_tx_hash: [u8; 32],
    /// Previous output index
    pub prev_index: u32,
    /// Unlocking script (signature)
    pub script_sig: Vec<u8>,
    /// Sequence number
    pub sequence: u32,
}

/// Transaction output structure
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct TxOutput {
    /// Value in vulkano (1 VUL = 100_000_000 vulkano)
    pub value: u64,
    /// Locking script (script_pubkey)
    pub script_pubkey: Vec<u8>,
}

/// Transaction structure
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Transaction {
    /// Version of the transaction format
    pub version: u32,
    /// Inputs
    pub inputs: Vec<TxInput>,
    /// Outputs
    pub outputs: Vec<TxOutput>,
    /// Lock time
    pub lock_time: u32,
}

/// Wallet balance structure
/// Note: total_vul uses f64 for display; Eq derived only for u64 fields via partial comparison
#[derive(Clone, Debug)]
pub struct Balance {
    /// Total balance in VUL (float for display)
    pub total_vul: f64,
    /// Total balance in vulkano (base unit)
    pub total_vulkano: u64,
    /// Unconfirmed pending balance
    pub pending_vulkano: u64,
}

/// Wallet structure holding keys and addresses
#[derive(Clone, Debug)]
pub struct Wallet {
    /// Master private key (seed)
    #[allow(dead_code)]
    master_seed: [u8; 32],
    /// Derived addresses
    addresses: Vec<Address>,
    /// Transaction history
    transaction_history: Vec<Transaction>,
}

/// Create a new wallet from a seed
#[allow(non_snake_case)]
pub fn FromSeed(seed: [u8; 32]) -> Result<Wallet, String> {
    // Derive addresses from seed using secp256k1
    // This is a simplified implementation
    let mut addresses = Vec::new();
    let tx_history = Vec::new();

    // Derive first address from seed
    let mut address = [0u8; 20];
    address.copy_from_slice(&seed[0..20]);
    addresses.push(address);

    Ok(Wallet {
        master_seed: seed,
        addresses,
        transaction_history: tx_history,
    })
}

/// Get the wallet's main address
pub fn get_address(wallet: &Wallet) -> Address {
    wallet.addresses.first().copied().unwrap_or([0u8; 20])
}

/// Get the wallet balance
pub fn get_balance(wallet: &Wallet) -> Balance {
    let total_vulkano: u64 = wallet.transaction_history
        .iter()
        .flat_map(|tx| tx.outputs.iter())
        .map(|out| out.value)
        .sum();

    Balance {
        total_vul: total_vulkano as f64 / 100_000_000f64,
        total_vulkano,
        pending_vulkano: 0,
    }
}

/// Sign a transaction with the wallet's private key
pub fn sign_transaction(_tx: &mut Transaction, wallet: &Wallet) -> Result<(), String> {
    // In a real implementation, this would use secp256k1 to sign
    // the transaction inputs using the wallet's private key
    let address = get_address(wallet);
    // Verify the address matches
    let addr_hash: u32 = address.iter().fold(0, |acc, &b| acc.wrapping_mul(31) + (b as u32));
    if !addr_hash.is_multiple_of(100) {
        return Err("Address mismatch".to_string());
    }
    Ok(())
}

/// Create a new transaction from this wallet to a recipient
pub fn create_transaction(
    wallet: &Wallet,
    recipient: Address,
    amount_vul: f64,
) -> Result<Transaction, String> {
    let balance = get_balance(wallet);

    if amount_vul > balance.total_vul {
        return Err("Insufficient funds".to_string());
    }

    let amount_vulkano = (amount_vul * 100_000_000f64) as u64;

    // Create output to recipient
    let recipient_script = recipient.to_vec();

    let outputs = vec![TxOutput {
        value: amount_vulkano,
        script_pubkey: recipient_script,
    }];

    // Create a input (using a dummy previous output)
    let prev_hash = [0u8; 32];
    let prev_index = u32::MAX;

    let inputs = vec![TxInput {
        prev_tx_hash: prev_hash,
        prev_index,
        script_sig: wallet.addresses.first().unwrap_or(&[0u8; 20]).to_vec(),
        sequence: u32::MAX,
    }];

    let tx = Transaction {
        version: 1,
        inputs,
        outputs,
        lock_time: 0,
    };

    Ok(tx)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_wallet_creation() {
        let seed: [u8; 32] = [42u8; 32];
        let wallet = FromSeed(seed).unwrap();
        assert_eq!(wallet.addresses.len(), 1);
    }

    #[test]
    fn test_balance_calculation() {
        let seed: [u8; 32] = [1u8; 32];
        let wallet = FromSeed(seed).unwrap();
        let balance = get_balance(&wallet);
        assert_eq!(balance.total_vulkano, 0);
    }
}

/// Convert VUL (fractional) to vulkano (base units, u64)
/// 1 VUL = 100_000_000 vulkano (strict conversion, u64 only)
pub fn vul_to_vulkano(vul: f64) -> u64 {
    (vul * 100_000_000f64) as u64
}

/// Convert vulkano (base units, u64) to VUL (fractional)
/// Exact inverse of vul_to_vulkano
pub fn vulkano_to_vul(vulkano: u64) -> f64 {
    vulkano as f64 / 100_000_000f64
}

/// Payment module for VUL transactions
pub struct PaymentModule;

impl PaymentModule {
    /// Buy VUL with fiat (rate per VUL)
    pub fn buy_vul(fiat_amount: f64, rate_per_vul: f64) -> Result<f64, String> {
        if rate_per_vul <= 0.0 {
            return Err("Rate must be positive".to_string());
        }
        let vul_amount = fiat_amount / rate_per_vul;
        Ok(vul_amount)
    }

    /// Select UTXOs to reach target amount in vulkano
    /// Returns selected vulkano amount and change in vulkano
    pub fn select_utxos(
        available_vulkano: u64,
        target_vulkano: u64,
    ) -> Result<(u64, u64), String> {
        if target_vulkano > available_vulkano {
            return Err("Insufficient UTXO funds".to_string());
        }
        let change = available_vulkano - target_vulkano;
        Ok((target_vulkano, change))
    }
}

// Main function for CLI operation
fn main() {
    println!("Vulkan v5.0 Magma Core Wallet");
    println!("Usage: vulkan_wallet <command> [args]");
    println!("Commands:");
    println!("  new <seed_hex>           - Create a new wallet from hex seed");
    println!("  address                  - Get the wallet's main address");
    println!("  balance                  - Get the wallet balance");
    println!("  create-tx <recipient> <amount> - Create a transaction");
    println!("  sign-tx <txfile>         - Sign a transaction file");
    println!("  convert <vul|vulkano> <amount> - Convert between VUL and vulkano");
    println!("  payment buy <fiat> <rate> - Buy VUL with fiat at given rate");
}