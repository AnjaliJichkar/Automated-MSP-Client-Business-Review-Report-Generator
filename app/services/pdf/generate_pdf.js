const puppeteer = require("puppeteer");
const fs = require("fs");
const path = require("path");

// Load Inter fonts as base64 for self-contained embedding
const FONTS_DIR = path.join(__dirname, "fonts");
const interRegularB64  = fs.readFileSync(path.join(FONTS_DIR, "Inter_28pt-Regular.ttf")).toString("base64");
const interMediumB64   = fs.readFileSync(path.join(FONTS_DIR, "Inter_28pt-Medium.ttf")).toString("base64");
const interSemiBoldB64 = fs.readFileSync(path.join(FONTS_DIR, "Inter_28pt-SemiBold.ttf")).toString("base64");
const interBoldB64     = fs.readFileSync(path.join(FONTS_DIR, "Inter_28pt-Bold.ttf")).toString("base64");

const FONT_CSS = `
  @font-face {
    font-family: "Inter";
    src: url("data:font/truetype;base64,${interRegularB64}") format("truetype");
    font-weight: 400;
    font-style: normal;
  }
  @font-face {
    font-family: "Inter";
    src: url("data:font/truetype;base64,${interMediumB64}") format("truetype");
    font-weight: 500;
    font-style: normal;
  }
  @font-face {
    font-family: "Inter";
    src: url("data:font/truetype;base64,${interSemiBoldB64}") format("truetype");
    font-weight: 600;
    font-style: normal;
  }
  @font-face {
    font-family: "Inter";
    src: url("data:font/truetype;base64,${interBoldB64}") format("truetype");
    font-weight: 700;
    font-style: normal;
  }
`;

/**
 * PRODUCTION PDF GENERATOR FROM HTML STRING
 *
 * Usage: node generate_pdf.js <htmlFilePath> <outputPdfPath>
 * - htmlFilePath: Path to temp file containing HTML content
 * - outputPdfPath: Where to save the generated PDF
 *
 * Maintains same CSS injection, page breaks, viewport, and formatting
 * Includes retry logic for reliability
 */

const CONFIG = {
  // Viewport - EXACTLY SAME AS ORIGINAL
  viewport: {
    width: 1600,
    height: 900,
  },

  // PDF settings - EXACTLY SAME AS ORIGINAL
  pdf: {
    format: "A4",
    landscape: true,
    printBackground: true,
    scale: 0.64,
    margin: {
      top: "10mm",
      right: "10mm",
      bottom: "10mm",
      left: "10mm",
    },
  },

  renderStabilizeDelay: 10000,
  maxRetries: 2,
  retryDelay: 1000,
};

// CSS to inject for print - EXACTLY SAME AS ORIGINAL
const PRINT_CSS = `
  @media print {
    @page {
      size: A4 landscape;
      margin: 10mm;
    }

    /* FRONT PAGE - ALWAYS ONE PAGE, MANDATORY PAGE BREAK AFTER */
    #pdf-front-page {
      min-height: 100vh !important;
      max-height: 100vh !important;
      height: 100vh !important;
      display: flex !important;
      flex-direction: column !important;
      justify-content: center !important;
      align-items: center !important;
      page-break-after: always !important;
      page-break-before: auto !important;
      page-break-inside: avoid !important;
      break-after: page !important;
      break-before: auto !important;
      break-inside: avoid !important;
      overflow: hidden !important;
      box-sizing: border-box !important;
      position: relative !important;
    }

    #pdf-front-page > .a4-landscape {
      width: 100% !important;
      height: 100% !important;
      max-height: 100vh !important;
      display: flex !important;
      flex-direction: column !important;
      justify-content: space-between !important;
      overflow: hidden !important;
    }

    /* First chart-section containing front page - enforce single page */
    .chart-section:first-of-type:has(#pdf-front-page),
    .pdf-page:first-child:has(#pdf-front-page),
    .pdf-page.first-page-cover {
      min-height: 100vh !important;
      max-height: 100vh !important;
      page-break-after: always !important;
      page-break-inside: avoid !important;
      break-after: page !important;
      break-inside: avoid !important;
      overflow: hidden !important;
    }

    /* Body/HTML - remove default margins, center content */
    body, html {
      margin: 0 !important;
      padding: 0 !important;
    }

    /* Main container - center content horizontally */
    .max-w-7xl {
      max-width: 100% !important;
      width: 100% !important;
      margin: 0 auto !important;
      padding: 0 !important;
    }

    /* Center all chart sections on page */
    .chart-section {
      display: flex !important;
      flex-direction: column !important;
      justify-content: center !important;
      width: 100% !important;
    }

    /* Report root - center content */
    #report-root {
      width: 100% !important;
    }

    /* Remove all borders from chart sections */
    .chart-section {
      border: none !important;
      box-shadow: none !important;
    }

    /* Remove borders from tables too */
    .module-enablement-table,
    table {
      border: none !important;
      box-shadow: none !important;
    }

    /* Cover page - fill exactly one page and clip overflow */
    .pdf-page.first-page-cover {
      height: 100vh !important;
      max-height: 100vh !important;
      overflow: hidden !important;
      page-break-after: always !important;
    }

    /* Reset pdf-page to allow 2 sections per page */
    .pdf-page {
      width: 100% !important;
      min-height: auto !important;
      height: auto !important;
      page-break-after: auto !important;
      break-after: auto !important;
      margin: 0 0 20px 0 !important;
      padding: 15px !important;
      box-sizing: border-box !important;
    }

    /* Chart sections - no transform to preserve Y-axis labels */
    .chart-section {
      page-break-inside: avoid !important;
      break-inside: avoid !important;
      margin-bottom: 15px !important;
    }

    /* Ensure charts don't overflow */
    .chart-section canvas,
    .chart-section svg {
      max-width: 100% !important;
      height: auto !important;
    }

    /* Tables should not break */
    table {
      page-break-inside: avoid !important;
    }

    /* KEEP HEADERS WITH THEIR CONTENT */
    h1, h2, h3, h4, h5, h6,
    [class*="title"], [class*="Title"],
    [class*="header"], [class*="Header"] {
      page-break-after: avoid !important;
      break-after: avoid !important;
    }

    /* Hide download button */
    #download-report-btn {
      display: none !important;
    }

    /* Hide export buttons */
    button.bg-green-600,
    button.bg-blue-600,
    .bg-green-600,
    .bg-blue-600 {
      display: none !important;
    }

    .flex.gap-2:has(button.bg-green-600),
    .flex.gap-2:has(button.bg-blue-600) {
      display: none !important;
    }

    /* Force page break after every 2nd section */
    .pdf-page:nth-child(2n) {
      page-break-after: always !important;
      break-after: page !important;
    }
  }
`;

/**
 * Generate PDF from HTML with retry logic
 */
async function generatePdfWithRetry(htmlFilePath, outputPath, attempt = 1) {
  let browser;

  try {
    console.log(`[Attempt ${attempt}/${CONFIG.maxRetries}] Starting PDF generation...`);

    // Validate input file exists
    if (!fs.existsSync(htmlFilePath)) {
      throw new Error(`HTML file not found: ${htmlFilePath}`);
    }

    // Launch browser
    console.log("Launching Chromium...");
    browser = await puppeteer.launch({
      headless: "new",
      protocolTimeout: 120000,  // 2 minutes for large reports
      args: [
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
      ],
    });

    const page = await browser.newPage();

    // Set viewport - EXACTLY SAME AS ORIGINAL
    await page.setViewport(CONFIG.viewport);
    console.log(`Viewport set to ${CONFIG.viewport.width}x${CONFIG.viewport.height}`);

    // Read HTML content from file
    console.log(`Reading HTML from: ${htmlFilePath}`);
    const htmlContent = fs.readFileSync(htmlFilePath, 'utf8');

    // Load HTML content into page
    console.log("Loading HTML content...");
    await page.setContent(htmlContent, {
      waitUntil: "domcontentloaded",
    });

    console.log("HTML content loaded");

    // Wait for dynamic content to render - EXACTLY SAME AS ORIGINAL
    console.log("Waiting for content to stabilize...");
    await new Promise(resolve => setTimeout(resolve, CONFIG.renderStabilizeDelay));

    console.log("Content ready for PDF generation");

    // Remove shadow-md class from all elements - EXACTLY SAME AS ORIGINAL
    console.log("Removing shadow-md class from all elements...");
    const removedCount = await page.evaluate(() => {
      const elementsWithShadow = document.querySelectorAll('[class*="shadow-md"]');
      let count = 0;
      elementsWithShadow.forEach(element => {
        if (element.classList.contains('shadow-md')) {
          element.classList.remove('shadow-md');
          count++;
        }
      });
      return count;
    });
    console.log(`Removed shadow-md from ${removedCount} elements`);

    // Apply print media type - EXACTLY SAME AS ORIGINAL
    await page.emulateMediaType('print');
    console.log("Print media type applied");

    // Inject Inter font first (must load before any rendering)
    await page.addStyleTag({ content: FONT_CSS });
    console.log("Inter font injected");

    // Inject custom CSS - EXACTLY SAME AS ORIGINAL
    await page.addStyleTag({ content: PRINT_CSS });
    console.log("Custom print CSS injected");

    // Small delay for CSS to apply - EXACTLY SAME AS ORIGINAL
    await new Promise(resolve => setTimeout(resolve, 500));

    // Generate PDF - EXACTLY SAME SETTINGS AS ORIGINAL
    console.log("Generating PDF (A4 Landscape, scale 0.64)...");
    await page.pdf({
      path: outputPath,
      format: CONFIG.pdf.format,
      landscape: CONFIG.pdf.landscape,
      printBackground: CONFIG.pdf.printBackground,
      scale: CONFIG.pdf.scale,
      margin: CONFIG.pdf.margin,
    });

    console.log(` PDF successfully generated: ${outputPath}`);

    // Close browser
    await browser.close();
    console.log("Browser closed");

    return { success: true, outputPath };

  } catch (error) {
    console.error(` PDF generation failed (Attempt ${attempt}/${CONFIG.maxRetries}):`, error.message);

    // Close browser if it's open
    if (browser) {
      try {
        await browser.close();
        console.log("Browser closed after error");
      } catch (closeError) {
        console.error("Failed to close browser:", closeError.message);
      }
    }

    // Retry if we haven't reached max attempts
    if (attempt < CONFIG.maxRetries) {
      console.log(`Retrying in ${CONFIG.retryDelay}ms...`);
      await new Promise(resolve => setTimeout(resolve, CONFIG.retryDelay));
      return generatePdfWithRetry(htmlFilePath, outputPath, attempt + 1);
    }

    // All retries exhausted
    throw new Error(`PDF generation failed after ${CONFIG.maxRetries} attempts: ${error.message}`);
  }
}

// Main execution
(async () => {
  // Parse command line arguments
  const args = process.argv.slice(2);

  if (args.length < 2) {
    console.error("Usage: node generatePdfFromHtml.js <htmlFilePath> <outputPdfPath>");
    process.exit(1);
  }

  const [htmlFilePath, outputPath] = args;

  try {
    await generatePdfWithRetry(htmlFilePath, outputPath);
    process.exit(0); // Success
  } catch (error) {
    console.error("FATAL ERROR:", error.message);
    process.exit(1); // Failure
  }
})();
