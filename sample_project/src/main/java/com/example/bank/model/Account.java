package com.example.bank.model;

import java.math.BigDecimal;

/**
 * A bank account with a balance and a lifecycle status.
 * Balance changes must go through {@link com.example.bank.service.AccountService}.
 */
public class Account {

    /** Lifecycle states of an account. */
    public enum Status {
        ACTIVE,
        FROZEN,
        CLOSED
    }

    private final String accountNumber;
    private BigDecimal balance;
    private Status status;

    public Account(String accountNumber, BigDecimal openingBalance) {
        this.accountNumber = accountNumber;
        this.balance = openingBalance;
        this.status = Status.ACTIVE;
    }

    public String getAccountNumber() {
        return accountNumber;
    }

    public BigDecimal getBalance() {
        return balance;
    }

    public Status getStatus() {
        return status;
    }

    /**
     * Applies a signed delta to the balance. Negative delta means withdrawal.
     *
     * @param delta signed amount to apply
     * @throws IllegalStateException if the account is not ACTIVE
     */
    void applyDelta(BigDecimal delta) {
        if (status != Status.ACTIVE) {
            throw new IllegalStateException("Account " + accountNumber + " is " + status);
        }
        this.balance = this.balance.add(delta);
    }

    void freeze() {
        this.status = Status.FROZEN;
    }
}
