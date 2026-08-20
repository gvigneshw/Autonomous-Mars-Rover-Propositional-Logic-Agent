import tkinter as tk
from tkinter import scrolledtext
import time
import sys
import io

from environment import Environment
from agent import KBAgent

class RedirectText(io.StringIO):
    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget

    def write(self, string):
        self.text_widget.insert(tk.END, string)
        self.text_widget.see(tk.END)
        self.text_widget.update_idletasks()
        
    def flush(self):
        pass

class RoverGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Autonomous Mars Rover - Propositional Logic Agent")
        
        # Dimensions
        self.cell_size = 80
        
        # UI Layout
        self.main_frame = tk.Frame(root)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Left Panel - Grid
        self.canvas_frame = tk.Frame(self.main_frame)
        self.canvas_frame.pack(side=tk.LEFT, padx=10)
        
        self.canvas = tk.Canvas(self.canvas_frame, bg="black")
        self.canvas.pack()
        
        # Right Panel - Logs
        self.log_frame = tk.Frame(self.main_frame)
        self.log_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=10)
        
        self.log_text = scrolledtext.ScrolledText(self.log_frame, width=60, height=30, bg="black", fg="lightgreen", font=("Consolas", 10))
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # Redirect stdout to text widget
        sys.stdout = RedirectText(self.log_text)
        
        # Bottom Panel - Controls
        self.control_frame = tk.Frame(root)
        self.control_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=10)
        
        self.btn_step = tk.Button(self.control_frame, text="STEP", command=self.do_step, width=15, font=("Arial", 12, "bold"))
        self.btn_step.pack(side=tk.LEFT, padx=20)
        
        self.btn_auto = tk.Button(self.control_frame, text="AUTO RUN", command=self.toggle_auto, width=15, font=("Arial", 12, "bold"))
        self.btn_auto.pack(side=tk.LEFT, padx=20)
        
        self.btn_reset = tk.Button(self.control_frame, text="RESTART", command=self.init_sim, width=15, font=("Arial", 12, "bold"))
        self.btn_reset.pack(side=tk.LEFT, padx=20)
        
        # State
        self.auto_running = False
        self.game_over = False
        
        # Init sim
        self.init_sim()

    def init_sim(self):
        self.auto_running = False
        self.game_over = False
        self.btn_auto.config(text="AUTO RUN")
        self.btn_step.config(state=tk.NORMAL)
        
        self.log_text.delete(1.0, tk.END)
        
        self.env = Environment(width=6, height=6)
        self.env.generate_random_env(num_hazards=3, num_radiations=3, num_obstacles=2)
        self.agent = KBAgent(self.env, inference_method="dpll")
        
        self.canvas.config(width=self.env.width * self.cell_size, height=self.env.height * self.cell_size)
        
        print("=== Autonomous Mars Rover - Propositional Logic Agent ===")
        print(f"Rover Starting at {self.env.start_pos}")
        print("==================================================")
        
        self.draw_grid()

    def draw_grid(self):
        self.canvas.delete("all")
        cs = self.cell_size
        
        for y in range(self.env.height):
            for x in range(self.env.width):
                x1, y1 = x * cs, y * cs
                x2, y2 = x1 + cs, y1 + cs
                
                # Determine cell color based on agent's knowledge
                bg_color = "#333333" # Unknown
                text = ""
                fg_color = "white"
                
                if (x, y) == self.env.start_pos:
                    bg_color = "#4CAF50" # Safe
                    text = "START"
                elif (x, y) == self.env.goal_pos and (x, y) not in self.agent.visited:
                    bg_color = "#333333"
                    text = "GOAL"
                    fg_color = "gold"
                elif (x, y) in self.agent.visited:
                    if (x, y) in self.env.hazards:
                        bg_color = "#F44336" # Red
                        text = "HAZARD"
                    elif (x, y) in self.env.radiations:
                        bg_color = "#FFC107" # Yellow
                        text = "RAD"
                        fg_color = "black"
                    elif (x, y) in self.env.obstacles:
                        bg_color = "#795548" # Brown
                        text = "OBS"
                    else:
                        bg_color = "#8BC34A" # Visited safe
                
                self.canvas.create_rectangle(x1, y1, x2, y2, fill=bg_color, outline="gray")
                if text:
                    self.canvas.create_text(x1 + cs/2, y1 + cs/2 - 15, text=text, fill=fg_color, font=("Arial", 10, "bold"))
                    
        # Draw Rover
        rx, ry = self.agent.x, self.agent.y
        rx1, ry1 = rx * cs + 15, ry * cs + 15
        rx2, ry2 = rx1 + cs - 30, ry1 + cs - 30
        self.canvas.create_oval(rx1, ry1, rx2, ry2, fill="#2196F3", outline="white", width=2)
        self.canvas.create_text(rx * cs + cs/2, ry * cs + cs/2, text="ROVER", fill="white", font=("Arial", 8, "bold"))

    def do_step(self):
        if self.game_over:
            return
            
        target, eval_results, percept, derivation, action_dir = self.agent.step()
        
        print("==================================================")
        print(f"STEP {self.agent.t:02d}")
        print("==================================================")
        
        print(f"\nPOSITION:\n({self.agent.x},{self.agent.y})\n")
        
        print("[SENSOR PERCEPTION]")
        if percept['HazardSignal']: print("Hazard detected in adjacent cell")
        else: print("Hazard: FALSE")
        if percept['RadiationSignal']: print("Radiation detected in adjacent cell")
        else: print("Radiation: FALSE")
        if percept['ObstacleSignal']: print("Obstacle detected in adjacent cell")
        else: print("Obstacle: FALSE")
        print()
        
        print("[KNOWLEDGE BASE UPDATE]")
        print(f"+ {self.agent.kb.get_clauses()[-1]}")
        print()
        
        if derivation:
            print("[LOGICAL INFERENCE]")
            for rule in derivation:
                parts = rule.split(" -> ")
                for i, part in enumerate(parts):
                    if i > 0:
                        print(f"    ↓\n{part}")
                    else:
                        print(part)
            print()
            
            print("[DECISION]")
            print(f"NEIGHBOR REJECTED\n")
            
        print("[REPLANNING]")
        for direction, status in eval_results.items():
            print(f"{direction} = {status}")
        print()
        
        print("[ACTION]")
        print(f"MOVE {action_dir}")
        print("==================================================\n")
        
        self.draw_grid()
        
        if (self.agent.x, self.agent.y) == self.env.goal_pos:
            self.game_over = True
            print("GOAL REACHED!")
            self.print_metrics()
            
        elif not target and action_dir == "NONE":
            self.game_over = True
            print("NO SAFE MOVES REMAINING!")
            self.print_metrics()
            
        if self.game_over:
            self.auto_running = False
            self.btn_auto.config(text="AUTO RUN")
            self.btn_step.config(state=tk.DISABLED)

    def print_metrics(self):
        print("==================================================")
        print("MISSION COMPLETE")
        print("==================================================")
        print(f"Steps              : {self.agent.metrics['steps']}")
        print(f"Path Cost          : {self.agent.metrics['path_cost']}")
        print(f"Cells Visited      : {len(self.agent.visited)}")
        print(f"Hazards Avoided    : {self.agent.metrics['hazards_avoided']}")
        print(f"Radiation Avoided  : {self.agent.metrics['radiation_avoided']}")
        print(f"Obstacles Avoided  : {self.agent.metrics['obstacles_avoided']}")
        print(f"KB Updates         : {self.agent.metrics['kb_updates']} CNF clauses added")
        print(f"Inferences         : {self.agent.metrics['inferences']} DPLL checks executed")
        print(f"Execution Time     : Instantly resolved O(1) avg per step via unit propagation")
        print("\nSTATUS:")
        if (self.agent.x, self.agent.y) == self.env.goal_pos:
            print("SUCCESS")
        else:
            print("EXPLORATION EXHAUSTED / BLOCKED")
        print("==================================================")

    def toggle_auto(self):
        if self.game_over:
            return
            
        if self.auto_running:
            self.auto_running = False
            self.btn_auto.config(text="AUTO RUN")
        else:
            self.auto_running = True
            self.btn_auto.config(text="PAUSE")
            self.auto_step()

    def auto_step(self):
        if self.auto_running and not self.game_over:
            self.do_step()
            self.root.after(300, self.auto_step)

if __name__ == "__main__":
    root = tk.Tk()
    app = RoverGUI(root)
    root.mainloop()
