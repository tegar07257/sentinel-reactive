// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.29;

import { Test } from "forge-std/Test.sol";
import { Sentinel } from "../src/Sentinel.sol";
import { SentinelCallback } from "../src/SentinelCallback.sol";
import { IReactive } from "@reactive/src/interfaces/IReactive.sol";
import { ISystemContract } from "@reactive/src/interfaces/ISystemContract.sol";
import { IPayable } from "@reactive/src/interfaces/IPayable.sol";

contract SentinelTest is Test {
    address internal constant SYSTEM_ADDR =
        0x8888888888888888888888888888888888888888;
    uint256 internal constant TRANSFER_TOPIC_0 =
        0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef;
    uint256 internal constant CRON100_TOPIC_0 =
        0xb49937fb8970e19fd46d48f7e3fb00d659deac0347f79cd7cb542f0fc1503c70;

    uint256 internal constant BASE_SEPOLIA = 84532;
    address internal constant TOKEN = 0x1111111111111111111111111111111111111111;
    address internal constant RECIPIENT =
        0x2222222222222222222222222222222222222222;

    Sentinel internal sentinel;
    SentinelCallback internal callbackContract;

    function setUp() public {
        // SYSTEM (0x8888..) has no code in the test env; forge reverts calls
        // to non-contract addresses. Etch a minimal stub so subscribe() and
        // requestCallbackV_1_0() calls succeed (empty returndata).
        vm.etch(SYSTEM_ADDR, hex"00");
        callbackContract = new SentinelCallback(
            IPayable(payable(address(0x3333333333333333333333333333333333333333))),
            address(this)
        );
        sentinel = new Sentinel(
            BASE_SEPOLIA,
            TOKEN,
            1000 ether,
            BASE_SEPOLIA,
            address(callbackContract),
            1_000_000
        );
    }

    function _transferLog(uint256 amount) internal pure returns (IReactive.LogRecord memory) {
        return
            IReactive.LogRecord({
                chainId: BASE_SEPOLIA,
                contractAddress: TOKEN,
                topic0: TRANSFER_TOPIC_0,
                topic1: uint256(uint160(address(0xAAAABBbbcccCDdDd11112222333344445555AaaA))),
                topic2: uint256(uint160(address(0xbBbbCcccDDDDAAAA111122223333444455556666))),
                topic3: 0,
                data: abi.encode(amount),
                blockNumber: 12345,
                opCode: 3,
                blockHash: 0,
                txHash: 0,
                logIndex: 0
            });
    }

    function test_react_reverts_when_not_system() public {
        vm.expectRevert();
        sentinel.react(_transferLog(2000 ether));
    }

    function test_large_transfer_counts_and_requests_callback() public {
        vm.expectCall(
            SYSTEM_ADDR,
            abi.encodeCall(
                ISystemContract.requestCallbackV_1_0,
                (
                    ISystemContract.CallbackConfiguration_V_1_0({
                        chainId: BASE_SEPOLIA,
                        recipient: address(callbackContract),
                        gasLimit: 1_000_000,
                        payload: abi.encodeWithSignature(
                            "alert(address,uint256,uint256)",
                            address(sentinel),
                            1,
                            2000 ether
                        )
                    })
                )
            )
        );
        vm.prank(SYSTEM_ADDR);
        sentinel.react(_transferLog(2000 ether));
        assertEq(sentinel.largeSellCount(), 1);
        assertEq(sentinel.lastLargeSellAmount(), 2000 ether);
        assertEq(sentinel.lastLargeSellBlock(), 12345);
    }

    function test_small_transfer_ignored_no_callback() public {
        vm.recordLogs();
        vm.prank(SYSTEM_ADDR);
        sentinel.react(_transferLog(999 ether));
        assertEq(sentinel.largeSellCount(), 0);
        assertEq(vm.getRecordedLogs().length, 0);
    }

    function test_cron_tick_recorded() public {
        IReactive.LogRecord memory log_ = _transferLog(0);
        log_.topic0 = CRON100_TOPIC_0;
        log_.opCode = 1;
        vm.roll(777);
        vm.prank(SYSTEM_ADDR);
        sentinel.react(log_);
        assertEq(sentinel.lastCronBlock(), 777);
    }

    function test_callback_rejects_wrong_sender() public {
        vm.expectRevert();
        callbackContract.alert(address(0xdead), 1, 100);
    }

    function test_callback_accepts_authorized_sender() public {
        // callbackContract was constructed with callbackSender = address(this).
        callbackContract.alert(address(this), 3, 5000 ether);
        assertEq(callbackContract.lastAlertCount(), 3);
        assertEq(callbackContract.lastAlertAmount(), 5000 ether);
    }
}
