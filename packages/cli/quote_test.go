package main

import (
	"io"
	"strings"
	"testing"

	"github.com/urfave/cli/v2"
)

func runQuote(args ...string) error {
	app := &cli.App{
		Name:      "ryskV12",
		Commands:  []*cli.Command{quoteAction},
		Writer:    io.Discard,
		ErrWriter: io.Discard,
	}
	return app.Run(append([]string{"ryskV12", "quote"}, args...))
}

// valid_until is read with c.Int64, which returns 0 for a value it cannot
// parse. As a string flag, a non-numeric value got past the flag parser and
// the quote was signed and sent with validUntil 0.
func TestQuoteRejectsNonNumericValidUntil(t *testing.T) {
	for _, value := range []string{"soon", "1730000000.5", "2026-11-05T12:00:00Z"} {
		t.Run(value, func(t *testing.T) {
			err := runQuote(
				"--channel_id", "rysk-test-no-such-channel",
				"--rfq_id", "1",
				"--asset", "0xb67bfa7b488df4f2efa874f4e59242e9130ae61f",
				"--chain_id", "84532",
				"--expiry", "1767225600",
				"--maker", testKeyAddress(t).Hex(),
				"--nonce", "1",
				"--price", "1000000",
				"--quantity", "1000000000000000000",
				"--strike", "3000000000000000000000",
				"--valid_until", value,
				"--usd", "0x98d56648c9b7f3cb49531f4135115b5000ab1733",
				"--collateral", "0x98d56648c9b7f3cb49531f4135115b5000ab1733",
				"--private_key", testPrivateKey,
			)
			if err == nil || !strings.Contains(err.Error(), "valid_until") {
				t.Fatalf("got error %v, want a valid_until parse error", err)
			}
		})
	}
}
