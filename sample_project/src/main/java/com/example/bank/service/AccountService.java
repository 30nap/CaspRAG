package com.example.bank.service;

import com.example.bank.model.Account;

import java.math.BigDecimal;
import java.util.Map;
import java.util.NoSuchElementException;
import java.util.concurrent.ConcurrentHashMap;

/**
 * In-memory implementation of {@link AccountOperations}.
 * In the real system this is backed by the core banking database and runs
 * inside a Spring-managed transaction.
 */
public class AccountService extends BaseService implements AccountOperations {

    private final Map<String, Account> accounts = new ConcurrentHashMap<>();

    public void register(Account account) {
        accounts.put(account.getAccountNumber(), account);
    }

    @Override
    public Account requireAccount(String accountNumber) {
        Account account = accounts.get(accountNumber);
        if (account == null) {
            throw new NoSuchElementException("No account " + accountNumber);
        }
        return account;
    }

    /**
     * {@inheritDoc}
     *
     * <p>Debits the source first; if crediting the target fails the debit is
     * compensated so that no money is lost.</p>
     */
    @Override
    public void transfer(String sourceAccount, String targetAccount, BigDecimal amount) {
        Account source = requireAccount(sourceAccount);
        Account target = requireAccount(targetAccount);
        if (source.getBalance().compareTo(amount) < 0) {
            throw new IllegalArgumentException("Insufficient funds on " + sourceAccount);
        }
        source.applyDelta(amount.negate());
        try {
            target.applyDelta(amount);
        } catch (RuntimeException e) {
            source.applyDelta(amount); // compensate the debit
            throw e;
        }
        audit("TRANSFER", sourceAccount + "->" + targetAccount + " " + amount);
    }
}
