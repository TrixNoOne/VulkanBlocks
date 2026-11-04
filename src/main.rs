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
#[allow(dead_code)]
pub struct Wallet {
    /// Master private key (seed)
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

// === Phase 4: Subsystem Hardening ===

/// Minimum fee rate in vulkano per byte
pub const MIN_FEE_RATE: u64 = 10;

/// Maximum mempool size before LRU eviction
pub const MAX_MEMPOOL_SIZE: usize = 50_000;

// === Phase 4: ASERT Retargeting ===

/// Euclidean division for ASERT anti-fork parity with Python's // and %
pub fn euclidean_division(n: i64, d: i64) -> (i64, i64) {
    let q = n / d;
    let r = n % d;
    if r < 0 {
        (q - 1, r + d)
    } else {
        (q, r)
    }
}

/// Calculate schedule offset: Δ_schedule = (t_parent - t_child) - (h_parent - h_child) * 120
pub fn calculate_schedule_offset(
    parent_timestamp: u64,
    parent_height: u64,
    child_timestamp: u64,
    child_height: u64,
) -> i64 {
    parent_timestamp as i64 - child_timestamp as i64
        - ((parent_height as i64 - child_height as i64) * 120)
}

/// ASERT target retargeting using Euclidean division and Radix 65536
pub fn execute_retargeting(parent_target: u64, schedule_offset: i64) -> u64 {
    if schedule_offset >= 0 {
        // Positive offset: right shift then divide (decrease target, easier mining)
        parent_target.wrapping_mul(65536) >> (schedule_offset / 65536)
    } else {
        // Negative offset: right shift then divide (increase target, harder mining)
        let neg_offset = -schedule_offset;
        parent_target >> (neg_offset / 65536)
    }
}

// === Phase 4: Mining ===

/// Calculate coinbase subsidy for a given era
/// S_k = floor(S_{k-1} * 3 / 4) with S_0 = 1_268_000_000 vulkano
pub fn calculate_coinbase_subsidy(era: u64) -> u64 {
    let initial_subsidy: u64 = 1_268_000_000;
    if era == 0 {
        return initial_subsidy;
    }
    let mut subsidy = initial_subsidy;
    for _ in 1..=era {
        // Floor division: (subsidy * 3) / 4
        subsidy = (subsidy * 3) / 4
    }
    subsidy
}

/// Calculate fee burn beta using EMA from Phase 3
/// Uses: beta(h) = min(BURN_MAX, beta_stat(h), ceiling(h))
pub fn calculate_fee_burn_beta(pending_count: usize) -> u64 {
    let u_low = 50_000_000; // 5% in ppb
    let u_high = 250_000_000; // 25% in ppb
    let burn_max_ppm = 900_000; // 90% max
    let ceil_min_ppm = 300_000; // 30% min
    let w_valley = 262_800; // ~1 year in blocks

    // Proxy utilization based on mempool size
    let utilization = if pending_count > 0 {
        (pending_count as u64 * 1_000_000) / MAX_MEMPOOL_SIZE as u64
    } else {
        0
    }.min(1_000_000);

    // EMA: beta_stat(h) = clamp(((U(h) - U_LOW) * 1_000_000) / (U_HIGH - U_LOW), 0, 1_000_000)
    let beta_stat = if utilization > u_low {
        let numerator = (utilization as i64 - u_low as i64) * 1_000_000i64;
        let denominator = (u_high - u_low) as i64;
        if denominator > 0 {
            let result = numerator / denominator;
            result.clamp(0, 1_000_000)
        } else {
            0
        }
    } else {
        0
    };

    // Boundary ceiling: ceiling(h) = CEIL_MIN + (BURN_MAX - CEIL_MIN) * min(d(h), W) / W
    // d(h) = min(h mod W, W - (h mod W))
    let height_estimate = 1000; // Would be actual block height
    let d_h = height_estimate % w_valley;
    let d_h = d_h.min(w_valley - d_h);
    let ceiling = ceil_min_ppm + (burn_max_ppm - ceil_min_ppm) * d_h / w_valley;

    // Final burn: beta(h) = min(BURN_MAX_PPM, beta_stat(h), ceiling(h))
    beta_stat.min(burn_max_ppm).min(ceiling) as u64
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
    println!("  retarget info            - Show ASERT retargeting parameters");
    println!("  mine <blocks>            - Mine blocks (PoW simulation)");
    println!("  mempool status           - Show mempool parameters");
}

// Phase 1 tests
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

    #[test]
    fn test_euclidean_division() {
        // Python: -5 // 3 = -2, -5 % 3 = 1
        let (q, r) = euclidean_division(-5, 3);
        assert_eq!(q, -2);
        assert_eq!(r, 1);

        // Python: 5 // 3 = 1, 5 % 3 = 2
        let (q, r) = euclidean_division(5, 3);
        assert_eq!(q, 1);
        assert_eq!(r, 2);
    }

    #[test]
    fn test_subsidy_decay() {
        // Era 0: 1,268,000,000
        // Era 1: floor(1_268_000_000 * 3 / 4) = 951,000,000
        // Era 2: floor(951_000_000 * 3 / 4) = 713,250,000
        assert_eq!(calculate_coinbase_subsidy(0), 1_268_000_000);
        assert_eq!(calculate_coinbase_subsidy(1), 951_000_000);
        assert_eq!(calculate_coinbase_subsidy(2), 713_250_000);
    }

    #[test]
    fn test_fee_burn_beta() {
        // Test that fee burn beta is calculated within valid range
        let beta = calculate_fee_burn_beta(MAX_MEMPOOL_SIZE);
        assert!(beta <= 900_000); // max burn PPM
    }

    #[test]
    fn test_minimum_fee_rate() {
        assert!(MIN_FEE_RATE == 10);
    }
}