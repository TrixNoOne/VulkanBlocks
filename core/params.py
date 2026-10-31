"""Costanti di consenso di Vulcan.

Unica fonte di verita': nessun parametro e' modificabile a runtime e non
esistono chiavi amministrative. I valori sono congelati qui e nel genesis, e
cambiano solo con un hard fork del software.
"""

# Unita' minime per 1 Vulcan (10^-8).
UNITS_PER_VULCAN = 100_000_000

# Sussidio iniziale: 3.1452 Vulcan per blocco; dimezzato ogni HALVING_INTERVAL.
BLOCK_SUBSIDY = 314_520_000

# L'halving avviene ogni 1_051_200 blocchi (~4 anni a 120 s/blocco).
HALVING_INTERVAL = 1_051_200

# Massa monetaria massima rappresentabile in unita' minime (32 miliardi).
# 3_200_000_000_000_000_000 < 2^63 = 9_223_372_036_854_775_808.
MAX_MONEY = 32_000_000_000 * UNITS_PER_VULCAN


def block_subsidy(height: int, *, halving_interval: int = HALVING_INTERVAL) -> int:
    """Sussidio per il blocco all'altezza *height*: dimezzamento per shift.

    Dopo 64 halving il sussidio e' 0 per sempre (shift >= 64 azzera un int64).
    Funzione pura, solo interi.
    """
    if not isinstance(height, int) or isinstance(height, bool) or height < 0:
        raise ValueError("height must be a non-negative int")
    if not isinstance(halving_interval, int) or isinstance(halving_interval, bool):
        raise ValueError("halving_interval must be an int")
    if halving_interval < 1:
        raise ValueError("halving_interval must be positive")
    era = height // halving_interval
    if era >= 64:
        return 0
    return BLOCK_SUBSIDY >> era

# Un output coinbase e' spendibile solo dopo questo numero di blocchi.
COINBASE_MATURITY = 100

# Regole temporali.
MTP_WINDOW = 11
MAX_FUTURE_DRIFT = 2 * 60 * 60

# Limiti di blocco e script.
MAX_BLOCK_SIZE = 1_000_000
MAX_SCRIPT_SIZE = 10_000
MAX_SCRIPT_ELEMENT_SIZE = 520
MAX_OPS_PER_SCRIPT = 201
MAX_STACK_ITEMS = 1_000
# Limite conservativo di opcode non-push valutati in un intero blocco.
MAX_BLOCK_SCRIPT_OPS = 10_000

# La coinbase deve iniziare con l'altezza (stile BIP34).
MIN_COINBASE_SCRIPT_SIG = 2
MAX_COINBASE_SCRIPT_SIG = 100

# Difficolta': ASERT a ogni blocco, tempo obiettivo 120 s, emivita 12 ore.
# Il riferimento e' sempre il genesis: niente ritarget periodico e nessun
# aggiustamento basato sulle fee.
TARGET_SPACING = 120
HALF_LIFE = 43_200

# Limiti assoluti del target a 512 bit.
MIN_TARGET = 1
MAX_TARGET = (1 << 512) - 1

# Locktime espresso in altezza: sopra questa soglia sarebbero timestamp.
LOCKTIME_THRESHOLD = 500_000_000

# Tag di rete: entrano nel sighash e impediscono replay tra reti.
NETWORK_MAIN = b"vulcan-main"
NETWORK_TEST = b"vulcan-test"
NETWORK_TAGS = frozenset((NETWORK_MAIN, NETWORK_TEST))

# Unico tipo di sighash supportato.
SIGHASH_ALL = 1

# --- Genesis ---------------------------------------------------------------
# Il genesis e' un blocco fisso, senza premine e senza chiavi amministrative:
# l'unico output vale 0 e non e' spendibile (OP_RETURN), la coinbase contiene
# solo altezza 0 e un messaggio testuale.
GENESIS_VERSION = 1
GENESIS_TIMESTAMP = 1_793_318_400  # 2026-10-30 00:00:00 UTC
GENESIS_OUTPUT_VALUE = 0

GENESIS_MESSAGE_MAIN = b"Vulcan mainnet genesis 2026-10-30: no premine, no admin."
GENESIS_MESSAGE_TEST = b"Vulcan testnet genesis 2026-10-30: no premine, no admin."

# Pow-limit iniziale: MAX_TARGET >> 22, cioe' ~2^22 hash attesi per blocco.
# Un singolo PC in Python trova il nonce in pochi minuti (o meno).
GENESIS_POW_LIMIT = MAX_TARGET >> 22

# Nonce e hash del genesis, minati una volta con tools/mine_genesis.py.
# Sono costanti di consenso: cambiarle equivale a cambiare la rete.
GENESIS_NONCE_MAIN = 4_551_610
GENESIS_NONCE_TEST = 9_590_371
GENESIS_HASH_MAIN = bytes.fromhex(
    "000002ecc8d47753862b07d4e0561014a1d2bce87f3efd318623d47f2ed2a16d"
    "7057fc2136fde933ff20554fa3c30f9534e635b6851580da7168670f205b63bf"
)
GENESIS_HASH_TEST = bytes.fromhex(
    "000000550f518f099726aed01c5215d35a014248b930f07f6e322e2cc85a8894"
    "0bf1c152489140d2e82cd12040f6f01d63a02da9bcd1b8186d446515a069eb6f"
)
