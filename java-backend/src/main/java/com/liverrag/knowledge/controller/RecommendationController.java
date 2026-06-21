package com.liverrag.knowledge.controller;

import com.liverrag.knowledge.dto.RecommendRequest;
import com.liverrag.knowledge.dto.RecommendResponse;
import com.liverrag.knowledge.dto.RecommendationFeedbackRequest;
import com.liverrag.knowledge.dto.RecommendationFeedbackResponse;
import com.liverrag.knowledge.service.RecommendationService;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1")
public class RecommendationController {
    private final RecommendationService recommendationService;

    public RecommendationController(RecommendationService recommendationService) {
        this.recommendationService = recommendationService;
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
