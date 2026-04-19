#ifndef OBSERVE_E_GIMBAL_PACKETS_H
#define OBSERVE_E_GIMBAL_PACKETS_H

#include <stdint.h>

#define OBSERVE_E_GIMBAL_CONTROL_MAGIC 0x47494D42u
#define OBSERVE_E_ENVIRONMENT_PACKET_MAGIC 0x564C4D45u
#define OBSERVE_E_MAX_ENV_OBJECTS 8

#ifdef __GNUC__
#define OBSERVE_E_PACKED __attribute__((packed))
#else
#define OBSERVE_E_PACKED
#pragma pack(push, 1)
#endif

typedef struct OBSERVE_E_PACKED {
    uint32_t magic;
    uint32_t frame_index;
    float timestamp_sec;
    uint8_t target_locked;
    uint8_t measurement_source;
    uint16_t reserved0;
    float confidence;
    float curr_x;
    float curr_y;
    float curr_xv;
    float curr_yv;
    float curr_w;
    float curr_h;
    float pred_x;
    float pred_y;
    float pred_xv;
    float pred_yv;
    float pred_w;
    float pred_h;
    float measured_bbox_x1;
    float measured_bbox_y1;
    float measured_bbox_x2;
    float measured_bbox_y2;
    float predicted_bbox_x1;
    float predicted_bbox_y1;
    float predicted_bbox_x2;
    float predicted_bbox_y2;
    float next_center_x;
    float next_center_y;
    float pixel_error_x;
    float pixel_error_y;
    float normalized_error_x;
    float normalized_error_y;
    float yaw_error_deg;
    float pitch_error_deg;
    float yaw_rate_deg_per_sec;
    float pitch_rate_deg_per_sec;
    float box_width_deg;
    float box_height_deg;
    float vision_dt_sec;
    float projection_dt_sec;
    float vision_age_sec;
    float covariance_x;
    float covariance_y;
    float covariance_xv;
    float covariance_yv;
    float covariance_w;
    float covariance_h;
    float kalman_dt_sec;
    float process_noise_position;
    float process_noise_velocity;
    float process_noise_size;
    float measurement_noise_position;
    float measurement_noise_size;
    float initial_covariance;
    float horizontal_fov_deg;
    float vertical_fov_deg;
} ObserveEGimbalControlPacket;

typedef struct OBSERVE_E_PACKED {
    uint16_t class_id;
    uint16_t reserved0;
    float confidence;
    float x1;
    float y1;
    float x2;
    float y2;
    char label[24];
} ObserveEEnvironmentObject;

typedef struct OBSERVE_E_PACKED {
    uint32_t magic;
    uint32_t frame_index;
    float timestamp_sec;
    float vlm_confidence;
    uint8_t object_count;
    uint8_t reserved1[3];
    char short_summary[160];
    char priority_hazard[64];
    char recommended_action[64];
    ObserveEEnvironmentObject objects[OBSERVE_E_MAX_ENV_OBJECTS];
} ObserveEEnvironmentPacket;

#ifndef __GNUC__
#pragma pack(pop)
#endif

#endif
