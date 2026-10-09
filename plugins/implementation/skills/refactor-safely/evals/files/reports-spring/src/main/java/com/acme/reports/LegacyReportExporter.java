package com.acme.reports;

import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Component;

/** Fixed-width export from the old reporting system. */
@Component("legacyExporter")
public class LegacyReportExporter implements ReportExporter {
    @Override
    public byte[] export(String reportName, List<Map<String, Object>> rows) {
        StringBuilder out = new StringBuilder(String.format("%-20s%n", reportName.toUpperCase()));
        for (Map<String, Object> row : rows) {
            for (Object value : row.values()) {
                out.append(String.format("%-16.16s", value));
            }
            out.append(System.lineSeparator());
        }
        return out.toString().getBytes(StandardCharsets.US_ASCII);
    }
}
