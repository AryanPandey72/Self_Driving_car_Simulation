import pygame
import math
import random
import numpy as np

# Initialize Pygame
pygame.init()

# --- Constants and Configuration ---
# Screen setup
WIDTH, HEIGHT = 1000, 800

# Colors
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
BLUE = (0, 100, 255)
RED = (255, 50, 50)
GREEN = (50, 255, 50)
CYAN = (0, 255, 255)
YELLOW = (255, 255, 0)
GRAY = (128, 128, 128)
DARK_GRAY = (50, 50, 50)
ROAD_COLOR = (40, 40, 40)

# Road parameters are now static for a straight road
ROAD_WIDTH = 450
LANE_COUNT = 3
LANE_WIDTH = ROAD_WIDTH // LANE_COUNT
ROAD_LEFT = (WIDTH - ROAD_WIDTH) // 2
ROAD_RIGHT = ROAD_LEFT + ROAD_WIDTH
LANE_CENTERS = [ROAD_LEFT + LANE_WIDTH // 2 + i * LANE_WIDTH for i in range(LANE_COUNT)]


# Speed ranges adjusted as per your request
CAR_WIDTH, CAR_HEIGHT = 30, 50
PLAYER_SPEED_MIN, PLAYER_SPEED_MAX = 4.0, 5.0
NPC_SPEED_MIN, NPC_SPEED_MAX = 3.0, 4.5

# AI & Sensor Parameters
SENSOR_COUNT = 16
SENSOR_LENGTH = 200
CHANGE_LANE_DISTANCE = 150
REAR_THREAT_DISTANCE = 100


class Car:
    def __init__(self, x, y, lane, speed, color, is_player=False):
        """Initializes a Car object."""
        self.x = x
        self.y = y
        self.lane = lane
        self.speed = speed
        self.color = color
        self.is_player = is_player
        self.target_speed = PLAYER_SPEED_MAX if is_player else speed
        
        # Sensor attributes
        self.sensor_angles = [i * (360 / SENSOR_COUNT) for i in range(SENSOR_COUNT)]
        self.sensor_lines = []
        
        # Lane changing attributes
        self.changing_lane = False
        self.target_lane = lane
        self.change_progress = 0.0
        
        # Status attributes
        self.collided = False
        self.lane_decision = "Initializing..."
        self.last_lane_change_time = 0
        self.min_lane_change_interval = 60
        
        # Logic for handling stalemates
        self.stuck_timer = 0

    def draw(self, screen):
        """Draws the car and its sensors on the screen."""
        car_rect = pygame.Rect(self.x - CAR_WIDTH // 2, self.y - CAR_HEIGHT // 2, CAR_WIDTH, CAR_HEIGHT)
        pygame.draw.rect(screen, self.color, car_rect)
        
        window_width = CAR_WIDTH - 10
        window_height = CAR_HEIGHT // 3
        window_rect = pygame.Rect(self.x - window_width // 2, self.y - CAR_HEIGHT // 4, window_width, window_height)
        pygame.draw.rect(screen, BLACK, window_rect)
        
        if self.is_player:
            pygame.draw.circle(screen, YELLOW, (int(self.x), int(self.y - CAR_HEIGHT // 4)), 5)
            for line in self.sensor_lines:
                pygame.draw.line(screen, GREEN, line[0], line[1], 1)
            
            font = pygame.font.SysFont(None, 24)
            status_text = font.render(f"Decision: {self.lane_decision}", True, WHITE)
            screen.blit(status_text, (self.x - status_text.get_width()//2, self.y - 80))

    def move(self, all_cars, frame_count, player_car):
        """Handles the movement and logic of the car."""
        if self.collided:
            return

        # AI logic for player car
        if self.is_player:
            self.autonomous_drive(all_cars, frame_count)
        
        # Corrected Relative Speed Physics
        if not self.is_player:
            self.y += (player_car.speed - self.speed)
            if self.y > HEIGHT + CAR_HEIGHT * 2:
                # Respawn NPC cars further up to avoid popping in
                self.y = -CAR_HEIGHT * 5
                self.lane = random.randint(0, LANE_COUNT - 1)
                self.x = LANE_CENTERS[self.lane]
                self.speed = random.uniform(NPC_SPEED_MIN, NPC_SPEED_MAX)

        # Lane changing and positioning for a straight road
        if self.changing_lane:
            self.change_progress += 0.05
            start_x = LANE_CENTERS[self.lane]
            end_x = LANE_CENTERS[self.target_lane]
            self.x = start_x + (end_x - start_x) * self.change_progress
            
            if self.change_progress >= 1.0:
                self.lane = self.target_lane
                self.x = LANE_CENTERS[self.lane]
                self.changing_lane = False
                self.change_progress = 0.0
                self.last_lane_change_time = frame_count
        else:
            # For straight road, car just needs to correct to the lane center
            target_x = LANE_CENTERS[self.lane]
            self.x += (target_x - self.x) * 0.1

    def autonomous_drive(self, cars, frame_count):
        """The core AI logic for the self-driving car."""
        # Adjust speed. Deceleration is now 5x faster than acceleration.
        if abs(self.speed - self.target_speed) > 0.05:
            self.speed += 0.02 if self.speed < self.target_speed else -0.1
        else:
            self.speed = self.target_speed

        # --- RESTRUCTURED AI LOGIC TO PREVENT OSCILLATION ---
        
        # 1. High-priority check: If currently changing lanes, is it still safe?
        if self.changing_lane:
            if not self.is_lane_safe(cars, self.target_lane):
                self.lane_decision = "Target Unsafe! Aborting."
                self.changing_lane = False
                self.stuck_timer = 0 # Reset timer
                return # End decision-making for this frame

        front_car, front_dist = self.get_car_in_front(cars, self.lane)
        is_on_cooldown = (frame_count - self.last_lane_change_time) < self.min_lane_change_interval

        # 2. "BLOCKED" STATE: This logic runs only if a car is too close in front.
        if not self.changing_lane and front_car and front_dist < CHANGE_LANE_DISTANCE:
            # Try to find a safe lane to change to if not on cooldown
            if not is_on_cooldown:
                possible_lanes = []
                if self.lane > 0: possible_lanes.append(self.lane - 1)
                if self.lane < LANE_COUNT - 1: possible_lanes.append(self.lane + 1)
                
                safe_lanes = [lane for lane in possible_lanes if self.is_lane_safe(cars, lane)]
                
                if safe_lanes:
                    # Safe lane found, initiate change.
                    best_lane = max(safe_lanes, key=lambda l: self.get_car_in_front(cars, l)[1])
                    self.lane_decision = f"Changing to Lane {best_lane + 1}"
                    self.changing_lane = True
                    self.target_lane = best_lane
                    self.target_speed = PLAYER_SPEED_MAX
                    self.stuck_timer = 0 # Reset timer as we are taking action
                    return
            
            # If we are here, it means we are blocked and cannot change lanes. So, we must brake.
            self.stuck_timer += 1
            # If stuck for more than 5 seconds (300 frames at 60fps)
            if self.stuck_timer > 300: 
                self.lane_decision = "Stuck! Braking hard."
                self.target_speed = front_car.speed - 1.0 # Brake aggressively to force a gap
            else:
                self.lane_decision = "Slowing: No safe lane"
                self.target_speed = front_car.speed - 0.1 # Standard gentle braking
        
        # 3. "CLEAR" STATE: This only runs if the "BLOCKED" state is false.
        else:
            if not self.changing_lane:
                self.lane_decision = "Road clear"
                self.target_speed = PLAYER_SPEED_MAX
                self.stuck_timer = 0 # Reset timer as the road is clear

    def update_sensors_and_check_collision(self, cars):
        """Updates sensor lines and checks for imminent collisions."""
        self.sensor_lines = []
        if self.collided: return

        for angle in self.sensor_angles:
            rad_angle = math.radians(angle)
            end_x = self.x + math.sin(rad_angle) * SENSOR_LENGTH
            end_y = self.y - math.cos(rad_angle) * SENSOR_LENGTH
            self.sensor_lines.append(((self.x, self.y), (end_x, end_y)))

        player_rect = pygame.Rect(self.x - CAR_WIDTH/2, self.y - CAR_HEIGHT/2, CAR_WIDTH, CAR_HEIGHT)
        for car in cars:
            if car == self: continue
            car_rect = pygame.Rect(car.x - CAR_WIDTH/2, car.y - CAR_HEIGHT/2, CAR_WIDTH, CAR_HEIGHT)
            if player_rect.colliderect(car_rect):
                self.collided = True
                car.collided = True
                self.lane_decision = "CRASHED!"
                break

    def get_car_in_front(self, cars, lane):
        """Finds the closest car directly in front within a given lane."""
        closest_dist = float('inf')
        closest_car = None
        for car in cars:
            if car == self or car.is_player: continue
            if car.lane == lane and car.y < self.y:
                dist = self.y - car.y
                if dist < closest_dist:
                    closest_dist = dist
                    closest_car = car
        return closest_car, closest_dist

    def is_lane_safe(self, cars, lane):
        """
        Comprehensive Lane Safety Check
        Checks for cars in a "safety bubble" alongside, cars ahead, and faster cars from the rear.
        """
        # 1. Check for immediate proximity (blind spot check)
        for car in cars:
            if car == self or car.is_player: continue
            if car.lane == lane:
                if abs(self.y - car.y) < CAR_HEIGHT * 2.5:
                    return False

        # 2. Check for cars far ahead in the target lane
        front_car, front_dist = self.get_car_in_front(cars, lane)
        if front_car and front_dist < CHANGE_LANE_DISTANCE:
            return False

        # 3. Check for faster-approaching cars from the rear
        for car in cars:
            if car == self or car.is_player: continue
            if car.lane == lane and car.y > self.y:
                dist_behind = car.y - self.y
                if dist_behind < REAR_THREAT_DISTANCE and car.speed > self.speed:
                    return False

        return True

def draw_road(screen):
    """Draws a simple, straight road."""
    # Draw road base
    pygame.draw.rect(screen, ROAD_COLOR, (ROAD_LEFT, 0, ROAD_WIDTH, HEIGHT))
    
    # Draw lane dividers (dashed lines)
    for i in range(1, LANE_COUNT):
        x_pos = ROAD_LEFT + i * LANE_WIDTH
        for y_pos in range(0, HEIGHT, 40):
            pygame.draw.line(screen, DARK_GRAY, (x_pos, y_pos), (x_pos, y_pos + 20), 5)

    # Draw outer borders
    pygame.draw.line(screen, WHITE, (ROAD_LEFT, 0), (ROAD_LEFT, HEIGHT), 5)
    pygame.draw.line(screen, WHITE, (ROAD_RIGHT, 0), (ROAD_RIGHT, HEIGHT), 5)

def show_crash_message(screen):
    """Displays a crash message."""
    font = pygame.font.SysFont(None, 80)
    text = font.render("CRASHED!", True, RED)
    screen.blit(text, (WIDTH // 2 - text.get_width() // 2, HEIGHT // 2 - text.get_height() // 2))
    font_small = pygame.font.SysFont(None, 40)
    text_small = font_small.render("Restarting...", True, WHITE)
    screen.blit(text_small, (WIDTH // 2 - text_small.get_width() // 2, HEIGHT // 2 + 50))
    pygame.display.flip()
    pygame.time.delay(2000)

def main():
    """Main game loop."""
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Self-Driving Car with Advanced AI")
    clock = pygame.time.Clock()
    
    def reset_simulation():
        player = Car(LANE_CENTERS[1], HEIGHT - 100, 1, PLAYER_SPEED_MIN, BLUE, True)
        all_cars = [player]
        for i in range(12):
            lane = random.randint(0, LANE_COUNT - 1)
            x_pos = LANE_CENTERS[lane]
            y_pos = random.randint(-HEIGHT, 0)
            speed = random.uniform(NPC_SPEED_MIN, NPC_SPEED_MAX)
            color = random.choice([RED, WHITE, GRAY])
            all_cars.append(Car(x_pos, y_pos, lane, speed, color))
        return player, all_cars, 0, 0

    player_car, cars, distance, frame_count = reset_simulation()
    running = True

    while running:
        frame_count += 1
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
        
        if player_car.collided:
            show_crash_message(screen)
            player_car, cars, distance, frame_count = reset_simulation()
            continue

        distance += player_car.speed

        for car in cars:
            car.move(cars, frame_count, player_car)
        
        player_car.update_sensors_and_check_collision(cars)

        screen.fill(DARK_GRAY)
        draw_road(screen)
        
        for car in sorted(cars, key=lambda c: c.y):
            car.draw(screen)

        font = pygame.font.SysFont(None, 36)
        speed_text = font.render(f"Speed: {player_car.speed * 10:.0f} km/h", True, GREEN)
        screen.blit(speed_text, (20, 20))
        lane_text = font.render(f"Lane: {player_car.lane + 1}", True, CYAN)
        screen.blit(lane_text, (20, 60))
        dist_text = font.render(f"Distance: {int(distance/100)}m", True, WHITE)
        screen.blit(dist_text, (20, 100))

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()

if __name__ == "__main__":
    main()
