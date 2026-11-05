package main

import (
	"context"
	"io"
	"math/big"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/ethereum/go-ethereum/crypto"
	"github.com/ethereum/go-ethereum/ethclient"
	"github.com/urfave/cli/v2"
)

func runApprove(args ...string) error {
	app := &cli.App{
		Name:      "ryskV12",
		Commands:  []*cli.Command{approveAction},
		Writer:    io.Discard,
		ErrWriter: io.Discard,
	}
	return app.Run(append([]string{"ryskV12", "approve"}, args...))
}

// An RPC endpoint that answers every call with a JSON-RPC error.
func failingRPC(t *testing.T) *httptest.Server {
	t.Helper()
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(`{"jsonrpc":"2.0","id":1,"error":{"code":-32000,"message":"rpc unavailable"}}`))
	}))
	t.Cleanup(server.Close)
	return server
}

// approve used to return ("", nil) when the nonce or gas price lookup failed,
// so the CLI printed an empty line and exited 0 without sending anything.
func TestApproveReturnsTransactionOptsError(t *testing.T) {
	key, err := crypto.HexToECDSA(testPrivateKey)
	if err != nil {
		t.Fatalf("HexToECDSA: %v", err)
	}
	account := Account{Public: crypto.PubkeyToAddress(key.PublicKey), Private: key}

	client, err := ethclient.Dial(failingRPC(t).URL)
	if err != nil {
		t.Fatalf("ethclient.Dial: %v", err)
	}
	defer client.Close()

	txHash, err := account.approve(
		context.Background(),
		CHAIN_ID_BASE_SEPOLIA,
		*client,
		big.NewInt(1),
		ADDRESSES[CHAIN_ID_BASE_SEPOLIA].StrikeAsset,
	)
	if err == nil {
		t.Fatalf("got txHash %q and no error, want the RPC error", txHash)
	}
	if !strings.Contains(err.Error(), "rpc unavailable") {
		t.Errorf("got error %v, want the RPC error", err)
	}
}

// --asset is checked as quote checks --premium_asset: a malformed address must
// not be turned into some other address by HexToAddress and approved.
func TestApproveRejectsInvalidAsset(t *testing.T) {
	for _, asset := range []string{"0xnot-an-address", "0x98d56648c9b7f3cb49531f4135115b5000ab17", "usdc"} {
		t.Run(asset, func(t *testing.T) {
			err := runApprove(
				"--chain_id", "84532",
				"--rpc_url", failingRPC(t).URL,
				"--amount", "1",
				"--private_key", testPrivateKey,
				"--asset", asset,
			)
			if err == nil || !strings.Contains(err.Error(), "invalid asset") {
				t.Fatalf("got error %v, want an invalid asset error", err)
			}
		})
	}
}
