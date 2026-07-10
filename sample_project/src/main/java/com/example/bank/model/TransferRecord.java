package com.example.bank.model;

import java.math.BigDecimal;

/**
 * One row of the daily transfer input file, as read by the batch job.
 *
 * @param sourceAccount  account number to debit
 * @param targetAccount  account number to credit
 * @param amount         positive transfer amount
 */
public record TransferRecord(String sourceAccount, String targetAccount, BigDecimal amount) {

    /** Validates the basic shape of the record without touching any account state. */
    public boolean isWellFormed() {
        return sourceAccount != null && targetAccount != null
                && amount != null && amount.signum() > 0;
    }
}
