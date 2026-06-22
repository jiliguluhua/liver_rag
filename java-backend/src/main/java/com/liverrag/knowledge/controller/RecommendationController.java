package com.liverrag.knowledge.controller;

import com.liverrag.knowledge.dto.ProfileAnalyzeRequest;
import com.liverrag.knowledge.dto.ProfileAnalyzeResponse;
import com.liverrag.knowledge.dto.RecommendRequest;
import com.liverrag.knowledge.dto.RecommendResponse;
import com.liverrag.knowledge.dto.RecommendationFeedbackRequest;
import com.liverrag.knowledge.dto.RecommendationFeedbackResponse;
import com.liverrag.knowledge.service.RecommendationService;
import com.liverrag.knowledge.service.SessionHistoryProfileService;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1")
public class RecommendationController {
    private final RecommendationService recommendationService;
    private final SessionHistoryProfileService sessionHistoryProfileService;

    public RecommendationController(RecommendationService recommendationService, SessionHistoryProfileService sessionHistoryProfileService) {
        this.recommendationService = recommendationService;
        this.sessionHistoryProfileService = sessionHistoryProfileService;
    }

    @PostMapping("/profile/analyze")
    public ProfileAnalyzeResponse analyzeProfile(@Valid @RequestBody ProfileAnalyzeRequest request) {
        return sessionHistoryProfileService.analyze(request);
    }

    @PostMapping("/recommend")
    public RecommendResponse recommend(@Valid @RequestBody RecommendRequest request) {
        return recommendationService.recommend(request);
    }

    @PostMapping("/recommend/feedback")
    public RecommendationFeedbackResponse feedback(@Valid @RequestBody RecommendationFeedbackRequest request) {
        return recommendationService.recordFeedback(request);
    }
}
