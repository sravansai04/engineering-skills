package com.acme.reports;

import java.util.List;
import java.util.Map;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class QuarterlyPartnerExportJob {
    private final Map<String, ReportExporter> exporters;
    private final ReportProperties props;
    private final PartnerFeedClient partnerFeed;

    public QuarterlyPartnerExportJob(Map<String, ReportExporter> exporters, ReportProperties props, PartnerFeedClient partnerFeed) {
        this.exporters = exporters;
        this.props = props;
        this.partnerFeed = partnerFeed;
    }

    // 06:00 on the first day of each quarter
    @Scheduled(cron = "0 0 6 1 1,4,7,10 *")
    public void exportQuarterlyReport() {
        ReportExporter exporter = exporters.get(props.quarterlyExporter());
        List<Map<String, Object>> rows = partnerFeed.loadQuarterRows();
        partnerFeed.submit(exporter.export("quarterly-partner-export", rows));
    }
}
