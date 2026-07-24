import { decodeXPaymentResponse, wrapFetchWithPayment } from "x402-fetch";

export interface X402PaymentResult {
  status: number;
  statusText: string;
  body: string;
  paymentResponse: unknown;
}

/**
 * Pays for an x402-gated resource using the given viem-compatible wallet client.
 * `wrapFetchWithPayment` handles the 402 negotiation: it retries the request once
 * with a signed `X-Payment` header after the server returns payment requirements.
 */
export async function payForResource(
  walletClient: Parameters<typeof wrapFetchWithPayment>[1],
  resourceUrl: string,
  label: string,
): Promise<X402PaymentResult> {
  const fetchWithPayment = wrapFetchWithPayment(fetch, walletClient);

  console.log(`[${label}] requesting ${resourceUrl}`);
  const response = await fetchWithPayment(resourceUrl);

  const paymentResponseHeader = response.headers.get("x-payment-response");
  const paymentResponse = paymentResponseHeader
    ? decodeXPaymentResponse(paymentResponseHeader)
    : undefined;
  if (paymentResponse) {
    console.log(`[${label}] payment settled:`, paymentResponse);
  }

  const body = await response.text();
  console.log(`[${label}] got ${response.status} ${response.statusText} from ${resourceUrl}`);
  console.log(`[${label}] response body:`, body.slice(0, 500));

  return { status: response.status, statusText: response.statusText, body, paymentResponse };
}
