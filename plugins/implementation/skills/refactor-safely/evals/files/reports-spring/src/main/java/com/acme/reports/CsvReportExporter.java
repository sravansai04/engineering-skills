package com.acme.reports;

import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import org.springframework.stereotype.Component;

@Component("csvExporter")
public class CsvReportExporter implements ReportExporter {
    @Override
    public byte[] export(String reportName, List<Map<String, Object>> rows) {
        if (rows.isEmpty()) {
            return new byte[0];
        }
        String header = String.join(",", rows.get(0).keySet());
        String body = rows.stream()
                .map(r -> r.values().stream().map(String::valueOf).collect(Collectors.joining(",")))
                .collect(Collectors.joining("\n"));
        return (header + "\n" + body).getBytes(StandardCharsets.UTF_8);
    }
}
