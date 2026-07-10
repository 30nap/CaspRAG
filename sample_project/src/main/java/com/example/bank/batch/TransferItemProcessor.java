package com.example.bank.batch;

import com.example.bank.model.TransferRecord;

/**
 * Batch processor step: validates each {@link TransferRecord} before it is
 * written. Malformed records are filtered out (returning null skips the item),
 * mirroring the Spring Batch ItemProcessor contract.
 */
public class TransferItemProcessor {

    private long skipped;

    /**
     * Returns the record unchanged when valid, or null to skip it.
     * Skipping is counted so the job summary can report it.
     */
    public TransferRecord process(TransferRecord item) {
        if (!item.isWellFormed()) {
            skipped++;
            return null;
        }
        return item;
    }

    public long getSkippedCount() {
        return skipped;
    }
}
