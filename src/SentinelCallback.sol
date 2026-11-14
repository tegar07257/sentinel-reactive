// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.29;

import { IPayable } from "@reactive/src/interfaces/IPayable.sol";
import { AbstractCallback } from "@reactive/src/base/AbstractCallback.sol";

/// @title SentinelCallback — counterparty on Base Sepolia (Minggu 1 scaffold)
/// @notice Receives `alert` callbacks from the Sentinel reactive contract.
/// Only the authorized reactive contract (via the callback proxy) may call it.
/// @dev `callbackProxy_` is the Reactive callback proxy on the destination
/// chain (see dev.reactive.network "Callback Contracts"). Minggu 2 fills the
/// real proxy address in the deploy script after verifying it in the docs.
contract SentinelCallback is AbstractCallback {
    uint256 public lastAlertCount;
    uint256 public lastAlertAmount;
    uint256 public lastAlertBlock;

    event Alert(uint256 indexed count, uint256 amount, uint256 blockNumber);

    constructor(
        IPayable callbackProxy_,
        address callbackSender_
    ) AbstractCallback(callbackProxy_, callbackSender_) {}

    function alert(
        address callbackSender_,
        uint256 count_,
        uint256 amount_
    ) external onlyCallbackSender(callbackSender_) {
        lastAlertCount = count_;
        lastAlertAmount = amount_;
        lastAlertBlock = block.number;
        emit Alert(count_, amount_, block.number);
    }
}
