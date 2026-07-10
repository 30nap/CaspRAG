package com.example.bank.service;

import com.example.bank.model.Account;

import java.math.BigDecimal;

/**
 * Read and transfer operations exposed to the batch layer.
 */
public interface AccountOperations {

    /** Loads an account by its number, or throws if it does not exist. */
    Account requireAccount(String accountNumber);

    /**
     * Moves {@code amount} from source to target atomically.
     * Implementations must either apply both legs or neither.
     */
    void transfer(String sourceAccount, String targetAccount, BigDecimal amount);
}
