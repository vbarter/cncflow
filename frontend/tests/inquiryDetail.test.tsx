import assert from "node:assert/strict"
import test, { afterEach } from "node:test"
import { JSDOM } from "jsdom"
import React from "react"
import { InquiryDetail } from "../src/pages/InquiryDetail"

const dom = new JSDOM("<!doctype html><html><body></body></html>", {
  url: "http://localhost/",
})
Object.assign(globalThis, {
  window: dom.window,
  document: dom.window.document,
  HTMLElement: dom.window.HTMLElement,
  HTMLAnchorElement: dom.window.HTMLAnchorElement,
  Node: dom.window.Node,
  MutationObserver: dom.window.MutationObserver,
  getComputedStyle: dom.window.getComputedStyle,
  IS_REACT_ACT_ENVIRONMENT: true,
})
Object.defineProperty(globalThis, "navigator", {
  configurable: true,
  value: dom.window.navigator,
})

const { cleanup, fireEvent, render, screen, waitFor } = await import("@testing-library/react")
const originalFetch = globalThis.fetch
const originalAnchorClick = dom.window.HTMLAnchorElement.prototype.click

afterEach(() => {
  cleanup()
  globalThis.fetch = originalFetch
  dom.window.HTMLAnchorElement.prototype.click = originalAnchorClick
})

function mockInquiry(files: Array<{ role: string; detected_type: string }>) {
  const calls: string[] = []
  globalThis.fetch = async input => {
    const url = String(input)
    calls.push(url)
    if (url === "/api/v1/inquiries/rfq%2F4513") {
      return new Response(JSON.stringify({
        id: "rfq/4513",
        title: "RFQ-20260913-4513",
        customer: "Freeze",
        parts: [{ id: "part/8", name: "XM8", qty: 1, status: "draft" }],
      }), { status: 200, headers: { "Content-Type": "application/json" } })
    }
    if (url === "/api/v1/parts/part%2F8/files") {
      return new Response(JSON.stringify(files), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    }
    throw new Error(`unexpected request: ${url}`)
  }
  return calls
}

test("有归档文件时在导出 PDF 左侧显示零件原件下载", async () => {
  const calls = mockInquiry([{ role: "step", detected_type: "step" }])
  let downloaded: HTMLAnchorElement | null = null
  dom.window.HTMLAnchorElement.prototype.click = function click() {
    downloaded = this
  }

  render(<InquiryDetail id="rfq/4513" go={() => {}} />)

  const originals = await screen.findByRole("button", { name: "下载零件原件" })
  const pdf = screen.getByRole("button", { name: "导出 PDF" })
  assert.ok(originals.compareDocumentPosition(pdf) & Node.DOCUMENT_POSITION_FOLLOWING)
  assert.deepEqual(calls, [
    "/api/v1/inquiries/rfq%2F4513",
    "/api/v1/parts/part%2F8/files",
  ])

  fireEvent.click(originals)
  assert.equal(downloaded?.getAttribute("href"), "/api/v1/inquiries/rfq%2F4513/originals.zip")
  assert.equal(downloaded?.download, "RFQ-20260913-4513-零件原件.zip")
})

test("无归档文件时不显示零件原件下载", async () => {
  const calls = mockInquiry([])

  render(<InquiryDetail id="rfq/4513" go={() => {}} />)

  await screen.findByText("1 个零件综合报价")
  await waitFor(() => assert.equal(calls.length, 2))
  assert.equal(screen.queryByRole("button", { name: "下载零件原件" }), null)
})
