package com.example.bank.batch;

import com.example.bank.model.TransferRecord;
import com.example.bank.service.AccountOperations;

import java.util.List;

/**
 * Wires the daily transfer job: read records, validate them, then apply each
 * transfer through {@link AccountOperations}. Chunk size is fixed at 100;
 * a failing chunk is retried once and then the whole job stops, so partial
 * files are never silently committed.
 */
public class TransferJobConfig {

    static final int CHUNK_SIZE = 100;

    private final AccountOperations accountOperations;
    private final TransferItemProcessor processor = new TransferItemProcessor();

    public TransferJobConfig(AccountOperations accountOperations) {
        this.accountOperations = accountOperations;
    }

    /**
     * Runs the job over an already-parsed list of records.
     *
     * @return number of transfers actually applied
     */
    public int runJob(List<TransferRecord> records) {
        int applied = 0;
        for (List<TransferRecord> chunk : partition(records, CHUNK_SIZE)) {
            applied += processChunk(chunk);
        }
        return applied;
    }

    /** Applies one chunk; a failure inside the chunk is retried exactly once. */
    private int processChunk(List<TransferRecord> chunk) {
        try {
            return applyAll(chunk);
        } catch (RuntimeException first) {
            return applyAll(chunk); // single retry, then propagate
        }
    }

    private int applyAll(List<TransferRecord> chunk) {
        int applied = 0;
        for (TransferRecord record : chunk) {
            TransferRecord valid = processor.process(record);
            if (valid == null) {
                continue;
            }
            accountOperations.transfer(
                    valid.sourceAccount(), valid.targetAccount(), valid.amount());
            applied++;
        }
        return applied;
    }

    private static List<List<TransferRecord>> partition(List<TransferRecord> records, int size) {
        return java.util.stream.IntStream.range(0, (records.size() + size - 1) / size)
                .mapToObj(i -> records.subList(i * size, Math.min(records.size(), (i + 1) * size)))
                .toList();
    }
}
