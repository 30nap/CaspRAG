package com.example.bank.service;

import java.util.logging.Logger;

/**
 * Common plumbing for all services: structured audit logging.
 */
public abstract class BaseService {

    protected final Logger log = Logger.getLogger(getClass().getName());

    /** Writes one audit line; never throws. */
    protected void audit(String action, String detail) {
        try {
            log.info(() -> "AUDIT " + action + " " + detail);
        } catch (RuntimeException ignored) {
            // auditing must never break business flow
        }
    }
}
