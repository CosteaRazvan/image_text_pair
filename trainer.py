import os
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from model import Model
from tqdm.notebook import tqdm
import matplotlib.pyplot as plt

class Trainer():
    def __init__(self, cfg, logger, train_loader, val_loader, test_loader):
        self.cfg = cfg
        self.logger = logger
        self.train_loader = train_loader
        self.test_loader = test_loader
        self.val_loader = val_loader

        self.model = None
        self.best_acc = 0.0

        self.train_losses = []
        self.train_accs = []
        self.val_losses = []
        self.val_accs = []

    def train(self):
        self.model = Model(
            self.cfg["vision_params"], 
            self.cfg["language_params"], 
            self.cfg["classifier_params"]
        ).to(self.cfg["device"])
        
        optimizer_obj = getattr(torch.optim, self.cfg["optimizer"])
        self.optimizer = optimizer_obj(self.model.parameters(), lr=self.cfg["lr"])

        loss_obj = getattr(nn, self.cfg["loss_fn"])
        self.loss_fn = loss_obj()

        if not os.path.exists("saved_models"):
            os.makedirs("saved_models")
        
        for epoch in range(self.cfg["epochs"]):
            self.logger.log(f"epoch: {epoch+1}")
            train_step_loss, train_step_acc = self.train_step()
            self.logger.log(f"train_step_loss: {train_step_loss} | train_step_acc = {train_step_acc}")
            
            val_step_loss, val_step_acc = self.val_step()
            self.logger.log(f"val_step_loss: {val_step_loss} | val_step_acc = {val_step_acc}")

            self.train_losses.append(train_step_loss)
            self.train_accs.append(train_step_acc)
            self.val_losses.append(val_step_loss)
            self.val_accs.append(val_step_acc)

            if val_step_acc > self.best_acc:
                self.best_acc = val_step_acc
                torch.save(self.model.state_dict(), f"saved_models/best_model_{self.cfg['exp_id']}.pt")
                self.logger.log("New model saved")

        self.plot()

    def train_step(self):
        self.model.train()
        total_loss = 0.0
        correct_preds = 0.0
        total_preds = 0

        for img_inputs, txt_input, labels in tqdm(self.train_loader):
            img_inputs, txt_input, labels = img_inputs.to(self.cfg["device"]), txt_input.to(self.cfg["device"]), labels.to(self.cfg["device"])

            self.optimizer.zero_grad()
            
            outputs = self.model(img_inputs, txt_input)
            loss = self.loss_fn(outputs, labels)

            loss.backward()
            self.optimizer.step()

            total_loss += loss.item()
            predictions = torch.argmax(outputs, dim=1)
            correct_preds += torch.sum(predictions == labels).item()
            total_preds += labels.shape[0]

        train_step_loss = total_loss / len(self.train_loader)
        train_step_acc = correct_preds / total_preds

        return train_step_loss, train_step_acc

    def val_step(self):
        self.model.eval()
        total_loss = 0.0
        correct_preds = 0.0
        total_preds = 0

        with torch.no_grad():
            for img_inputs, txt_input, labels in tqdm(self.val_loader):
                img_inputs, txt_input, labels = img_inputs.to(self.cfg["device"]), txt_input.to(self.cfg["device"]), labels.to(self.cfg["device"])

                outputs = self.model(img_inputs, txt_input)
                loss = self.loss_fn(outputs, labels)
        
                total_loss += loss.item()
                predictions = torch.argmax(outputs, dim=1)
                correct_preds += torch.sum(predictions == labels).item()
                total_preds += labels.shape[0]

        val_step_loss = total_loss / len(self.val_loader)
        val_step_acc = correct_preds / total_preds

        return val_step_loss, val_step_acc

    def test_step(self):
        output_df = pd.DataFrame(
            pd.read_csv(os.path.join(self.cfg["data_root_path"], "sample_submission.csv"))["id"]
        )
        predictions = []
                            
        best_model_path = f"saved_models/best_model_{self.cfg['exp_id']}.pt"
        best_model = Model(
            self.cfg["vision_params"], 
            self.cfg["language_params"], 
            self.cfg["classifier_params"]
        ).to(self.cfg["device"])
        best_model.load_state_dict(torch.load(best_model_path))
        best_model.eval()

        with torch.no_grad():
            for img_inputs, txt_input, labels in tqdm(self.test_loader):
                img_inputs, txt_input, labels = img_inputs.to(self.cfg["device"]), txt_input.to(self.cfg["device"]), labels.to(self.cfg["device"])
                outputs = best_model(img_inputs, txt_input)
                predictions.extend(list(torch.argmax(outputs, dim=1).cpu().numpy()))
                    
        predictions = np.array(predictions)      
        output_df["label"] = predictions

        if not os.path.exists("submissions"):
            os.makedirs("submissions")

        output_df.to_csv(f"submissions/submission_{self.cfg['exp_id']}.csv", index=False)
        self.logger.log("Test results saved")
        self.logger.log(f"Validation accuracy with best model: {self.best_acc}")

        correct_preds = 0.0
        total_preds = 0

        with torch.no_grad():
            for img_inputs, txt_input, labels in tqdm(self.val_loader):
                img_inputs, txt_input, labels = img_inputs.to(self.cfg["device"]), txt_input.to(self.cfg["device"]), labels.to(self.cfg["device"])

                outputs = best_model(img_inputs, txt_input)
        
                predictions = torch.argmax(outputs, dim=1)
                correct_preds += torch.sum(predictions == labels).item()
                total_preds += labels.shape[0]

        self.logger.log(f"Validation accuracy with best model: {correct_preds / total_preds}")
        

    def plot(self):
        if not os.path.exists("figures"):
            os.makedirs("figures")

        plt.plot(range(self.cfg["epochs"]), self.train_losses, label="train loss")
        plt.plot(range(self.cfg["epochs"]), self.val_losses, label="val loss")
        plt.legend()
        plt.title("Loss")
        plt.savefig(f"figures/{self.cfg['exp_id']}_loss.jpg")
        plt.close()
        
        plt.plot(range(self.cfg["epochs"]), self.train_accs, label="train acc")
        plt.plot(range(self.cfg["epochs"]), self.val_accs, label="val acc")
        plt.title("Accuracy")
        plt.savefig(f"figures/{self.cfg['exp_id']}_accuracy.jpg")
        plt.close()
