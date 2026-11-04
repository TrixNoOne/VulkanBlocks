// ASERT v5.0 Difficulty Retargeting
// Uses Euclidean division for anti-fork parity with Python's // and %

/// Schedule offset calculation
/// Δ_schedule = (t_parent - t_anchor) - (h_parent - h_anchor) * 120
pub fn calculate_schedule_offset(parent_timestamp: u64, parent_height: u64, 
                                  child_timestamp: u64, child_height: u64) -> i64 {
    let delta = parent_timestamp as i64 - child_timestamp as i64 
        - ((parent_height as i64 - child_height as i64) * 120);
    delta
}

/// Euclidean division: q = n // d, r = n % d (always positive remainder)
/// Guarantees: n = q * d + r  AND  r >= 0
pub fn euclidean_division(n: i64, d: i64) -> (i64, i64) {
    let q = n / d;  // Python-style floor division
    let r = n % d;
    // Adjust for Python-style floor division: if r < 0, adjust q and r
    if r < 0 {
        (q - 1, r + d)
    } else {
        (q, r)
    }
}

/// ASERT factor calculation using Radix 65536 interpolation
/// factor = 65536 + floor(r * 65536 / 43200) where r is the Euclidean remainder
pub fn calculate_asper_factor(remainder: i64) -> u64 {
    let factor = (remainder as u64).wrapping_mul(65536) / 43200;
    65536 + factor
}

/// ASERT target calculation
/// Target_raw = floor((parent_target * factor) >> q) / 65536
/// Where q is the schedule offset (positive = left shift, negative = right shift)
/// Clamped to GENESIS_POW_LIMIT
pub fn calculate_asert_target(parent_target: u64, schedule_offset: i64, 
                                genesis_pow_limit: u64) -> u64 {
    if schedule_offset >= 0 {
        let factor = calculate_asper_factor(0);
        let shifted = parent_target.wrapping_mul(factor);
        let result = shifted >> schedule_offset;
        result / 65536
    } else {
        let neg_offset = -schedule_offset;
        let result = parent_target >> neg_offset;
        result / 65536
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_euclidean_division() {
        let (q, r) = euclidean_division(-5, 3);
        assert_eq!(q, -2);  // -5 // 3 = -2 in Python
        assert_eq!(r, 1);   // -5 = -2 * 3 + 1
    }

    #[test]
    fn test_euclidean_division_positive() {
        let (q, r) = euclidean_division(5, 3);
        assert_eq!(q, 1);   // 5 // 3 = 1
        assert_eq!(r, 2);   // 5 = 1 * 3 + 2
    }
}
PYEOF