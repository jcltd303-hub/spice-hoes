package com.spicehoes.identity.backend

import com.spicehoes.identity.ServiceState

/**
 * Phase A/B backend: returns the target scene untouched so the transport,
 * validation and orchestration path can be proven end to end. It reports
 * identity_applied=false and accelerated=false, honestly.
 */
class MockIdentityBackend : IdentityBackend {
    @Volatile private var ready = false

    override fun initialize(progress: (ServiceState) -> Unit) {
        progress(ServiceState.RUNTIME_LOADING)
        progress(ServiceState.MODEL_LOADING)
        progress(ServiceState.ACCELERATOR_INITIALIZING)
        ready = true
    }

    override fun selfTest() {
        check(ready) { "mock backend not initialized" }
    }

    override fun health() = BackendHealth(
        backend = "mock",
        provider = "none",
        accelerated = false,
        modelLoaded = false,
        modelId = "passthrough",
        modelSha256 = null,
        identityApplied = false,
    )

    override fun transfer(reference: ByteArray, target: ByteArray, options: TransferOptions) =
        TransferResult(target)

    override fun close() {
        ready = false
    }
}
