import random

class Environment:
    def __init__(self, width=6, height=6):
        self.width = width
        self.height = height
        self.hazards = set()
        self.radiations = set()
        self.obstacles = set()
        self.start_pos = (0, 0)
        self.goal_pos = (width - 1, height - 1)
        
    def add_hazard(self, x, y):
        self.hazards.add((x, y))
        
    def add_radiation(self, x, y):
        self.radiations.add((x, y))

    def add_obstacle(self, x, y):
        self.obstacles.add((x, y))
        
    def is_in_bounds(self, x, y):
        return 0 <= x < self.width and 0 <= y < self.height
        
    def get_percepts(self, x, y):
        """Return a dictionary of percepts at the given location."""
        percepts = {
            'HazardSignal': False,
            'RadiationSignal': False,
            'ObstacleSignal': False,
            'Safe': False,
            'Bump': False
        }
        
        # Check adjacent cells for signals
        for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
            nx, ny = x + dx, y + dy
            if (nx, ny) in self.hazards:
                percepts['HazardSignal'] = True
            if (nx, ny) in self.radiations:
                percepts['RadiationSignal'] = True
            if (nx, ny) in self.obstacles:
                percepts['ObstacleSignal'] = True
                
        if (x, y) not in self.hazards and (x, y) not in self.radiations and (x, y) not in self.obstacles:
            percepts['Safe'] = True
            
        return percepts

    def generate_random_env(self, num_hazards=3, num_radiations=3, num_obstacles=2):
        """Generate a random environment by placing hazards, radiation, and obstacles."""
        positions = [(x, y) for x in range(self.width) for y in range(self.height)]
        positions.remove(self.start_pos)
        if self.goal_pos in positions:
            positions.remove(self.goal_pos)
            
        random.shuffle(positions)
        
        for _ in range(num_hazards):
            if positions:
                self.add_hazard(*positions.pop())
                
        for _ in range(num_radiations):
            if positions:
                self.add_radiation(*positions.pop())

        for _ in range(num_obstacles):
            if positions:
                self.add_obstacle(*positions.pop())
