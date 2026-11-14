// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.29;

import { Script } from "forge-std/Script.sol";
import { Sentinel } from "../src/Sentinel.sol";
import { SentinelCallback } from "../src/SentinelCallback.sol";
import { IPayable } from "@reactive/src/interfaces/IPayable.sol";

/// @notice Deploy SentinelCallback on Base Sepolia, then Sentinel on Lasna.
/// @dev Minggu 1: script only — live deploy BLOCKED until testnet Sepolia ETH
/// is available for the Reactive faucet (1 SepETH -> 100 lREACT).
/// Run with a fresh TESTNET-ONLY key; never the Agentic Wallet key.
///   1. forge script script/Deploy.s.sol:DeployCallback --rpc-url $BASE_SEPOLIA_RPC --broadcast
///   2. forge script script/Deploy.s.sol:DeploySentinel --rpc-url $LASNA_RPC --broadcast
contract DeployCallback is Script {
    function run() external {
        address payable callbackProxy = payable(vm.envAddress("CALLBACK_PROXY"));
        address sentinelPlaceholder = vm.envAddress("SENTINEL_PLACEHOLDER");
        vm.startBroadcast();
        new SentinelCallback(IPayable(callbackProxy), sentinelPlaceholder);
        vm.stopBroadcast();
    }
}

contract DeploySentinel is Script {
    function run() external {
        uint256 originChainId = 84532; // Base Sepolia
        address originToken = vm.envAddress("ORIGIN_TOKEN");
        uint256 threshold = vm.envUint("THRESHOLD");
        address callbackRecipient = vm.envAddress("CALLBACK_RECIPIENT");
        vm.startBroadcast();
        new Sentinel{ value: 0.05 ether }(
            originChainId,
            originToken,
            threshold,
            originChainId,
            callbackRecipient,
            1_000_000
        );
        vm.stopBroadcast();
    }
}
