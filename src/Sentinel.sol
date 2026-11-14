// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.29;

import { ISystemContract } from "@reactive/src/interfaces/ISystemContract.sol";
import { IReactive } from "@reactive/src/interfaces/IReactive.sol";
import { AbstractReactive } from "@reactive/src/base/AbstractReactive.sol";

/// @title Sentinel — Reactive Meets AI (Minggu 1 scaffold)
/// @notice Reactive contract on Lasna testnet. Subscribes to ERC-20 Transfer
/// events of one token on Base Sepolia and to Cron100 ticks. A transfer at or
/// above `threshold` counts as a "large sell": state is updated and an `alert`
/// callback is requested to the counterparty contract on Base Sepolia.
/// The AI classification step (local qwen2.5:1.5b, proven in the Cortensor
/// agent-loop demo) plugs in during Minggu 2: the off-chain agent reads
/// `largeSellCount` / `lastLargeSellAmount` and decides the callback payload.
/// @dev Minggu 1 scope: subscription + react() routing + callback request.
/// No mainnet, no real funds. Deploy target: Lasna (chain 5318007).
contract Sentinel is AbstractReactive {
    /// @notice keccak256("Transfer(address,address,uint256)")
    uint256 internal constant TRANSFER_TOPIC_0 =
        0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef;
    /// @notice Cron100 topic0 from Reactive docs (every ~100 blocks, ~2 min).
    uint256 internal constant CRON100_TOPIC_0 =
        0xb49937fb8970e19fd46d48f7e3fb00d659deac0347f79cd7cb542f0fc1503c70;
    /// @notice Legacy system contract address, emitter of Cron events.
    address internal constant LEGACY_SYSTEM_ADDR =
        0x0000000000000000000000000000000000fffFfF;

    uint256 public immutable originChainId;
    address public immutable originToken;
    uint256 public immutable threshold;
    uint256 public immutable callbackChainId;
    address public immutable callbackRecipient;
    uint64 public immutable callbackGasLimit;

    uint256 public largeSellCount;
    uint256 public lastLargeSellAmount;
    uint256 public lastLargeSellBlock;
    uint256 public lastCronBlock;

    event LargeSell(uint256 indexed count, uint256 amount, uint256 blockNumber);
    event CronTick(uint256 blockNumber);

    constructor(
        uint256 originChainId_,
        address originToken_,
        uint256 threshold_,
        uint256 callbackChainId_,
        address callbackRecipient_,
        uint64 callbackGasLimit_
    ) payable {
        originChainId = originChainId_;
        originToken = originToken_;
        threshold = threshold_;
        callbackChainId = callbackChainId_;
        callbackRecipient = callbackRecipient_;
        callbackGasLimit = callbackGasLimit_;

        SYSTEM.subscribe(
            originChainId_,
            originToken_,
            TRANSFER_TOPIC_0,
            REACTIVE_IGNORE,
            REACTIVE_IGNORE,
            REACTIVE_IGNORE
        );
        SYSTEM.subscribe(
            block.chainid,
            LEGACY_SYSTEM_ADDR,
            CRON100_TOPIC_0,
            REACTIVE_IGNORE,
            REACTIVE_IGNORE,
            REACTIVE_IGNORE
        );
    }

    /// @notice Settles outstanding debt to the system contract from this
    /// contract's own balance. Added after the 2026-11-14 trigger incident:
    /// without this wrapper, funds transferred directly to the contract are
    /// stranded when it falls into debt (a balance settles nothing on its
    /// own), and only an external `depositTo()` at the system contract can
    /// revive it. See ../TRIGGER-FIX-2026-11-14.md in the reactive-omni
    /// folder. Anyone may call this: it only ever pays the system contract.
    function coverDebt() external {
        _coverDebt();
    }

    /// @inheritdoc IReactive
    function react(LogRecord memory log_) external onlySystem {
        if (log_.topic0 == TRANSFER_TOPIC_0) {
            _onTransfer(log_);
        } else if (log_.topic0 == CRON100_TOPIC_0) {
            lastCronBlock = block.number;
            emit CronTick(block.number);
        }
        // Unknown topics fall through: reverting here would still be billed.
    }

    function _onTransfer(LogRecord memory log_) internal {
        // ERC-20 Transfer(address indexed from, address indexed to, uint256 value)
        // arrives as LOG3: from = topic1, to = topic2, value in data.
        if (log_.opCode != 3) return;
        uint256 amount = abi.decode(log_.data, (uint256));
        if (amount < threshold) return;
        largeSellCount += 1;
        lastLargeSellAmount = amount;
        lastLargeSellBlock = log_.blockNumber;
        emit LargeSell(largeSellCount, amount, log_.blockNumber);
        SYSTEM.requestCallbackV_1_0(
            ISystemContract.CallbackConfiguration_V_1_0({
                chainId: callbackChainId,
                recipient: callbackRecipient,
                gasLimit: callbackGasLimit,
                payload: abi.encodeWithSignature(
                    "alert(address,uint256,uint256)",
                    address(this),
                    largeSellCount,
                    amount
                )
            })
        );
    }
}
